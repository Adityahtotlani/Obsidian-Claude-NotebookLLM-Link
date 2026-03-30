#!/usr/bin/env python3
"""
Obsidian ↔ Claude ↔ NotebookLM Bridge
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import click

CONFIG_PATH = Path.home() / '.obsidian-bridge-config.json'
DEFAULT_VAULT = str(Path.home() / 'Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Notes')


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def get_api_key(cfg: dict) -> str:
    return cfg.get('anthropic_key') or os.environ.get('ANTHROPIC_API_KEY', '')


# ─── CLI root ────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """Claude-Obsidian-NotebookLM Bridge\n
    \b
    Typical workflow:
      bridge config --anthropic-key sk-ant-...
      bridge export --folder research --process --output ./bundle
      bridge save  --title "My Summary" --input summary.txt
    """


# ─── config ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option('--vault', help='Path to Obsidian vault')
@click.option('--anthropic-key', help='Anthropic API key (or set ANTHROPIC_API_KEY env var)')
@click.option('--gdrive-creds', help='Path to Google Drive OAuth credentials JSON')
@click.option('--show', is_flag=True, help='Print current config')
def config(vault, anthropic_key, gdrive_creds, show):
    """Configure the bridge (saved to ~/.obsidian-bridge-config.json)."""
    cfg = load_config()
    if show:
        display = dict(cfg)
        if 'anthropic_key' in display:
            display['anthropic_key'] = display['anthropic_key'][:10] + '...'
        click.echo(json.dumps(display, indent=2))
        return
    if vault:
        cfg['vault_path'] = vault
    if anthropic_key:
        cfg['anthropic_key'] = anthropic_key
    if gdrive_creds:
        cfg['gdrive_credentials'] = gdrive_creds
    if not cfg.get('vault_path'):
        cfg['vault_path'] = DEFAULT_VAULT
    save_config(cfg)
    click.echo(f"Config saved → {CONFIG_PATH}")


# ─── export ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option('--folder', '-f', default=None, help='Filter by vault sub-folder')
@click.option('--tag', '-t', multiple=True, help='Filter by tag (repeatable: -t ai -t research)')
@click.option('--since', '-s', default=None, help='Modified since date YYYY-MM-DD')
@click.option('--output', '-o', default='./notebooklm-export', show_default=True, help='Output directory')
@click.option('--process', is_flag=True, help='Summarize each note with Claude')
@click.option('--synthesize', is_flag=True, help='Merge + synthesize all notes into one document with Claude')
@click.option('--topic', default=None, help='Topic hint for synthesis (e.g. "AI research")')
@click.option('--merged', is_flag=True, help='Merge all notes into one file without AI')
@click.option('--push-drive', is_flag=True, help='Upload bundle to Google Drive for NotebookLM')
@click.option('--limit', default=0, type=int, help='Max notes to export (0 = no limit)')
def export(folder, tag, since, output, process, synthesize, topic, merged, push_drive, limit):
    """Export Obsidian notes as a NotebookLM-ready bundle."""
    sys.path.insert(0, str(Path(__file__).parent))
    from modules.vault import VaultReader
    from modules.exporter import Exporter

    cfg = load_config()
    vault_path = cfg.get('vault_path', DEFAULT_VAULT)

    if not Path(vault_path).exists():
        click.echo(f"Vault not found: {vault_path}\nRun: bridge config --vault <path>", err=True)
        raise SystemExit(1)

    click.echo(f"Vault: {vault_path}")
    reader = VaultReader(vault_path)

    since_date = datetime.strptime(since, '%Y-%m-%d').date() if since else None
    notes = reader.read_notes(
        folder=folder,
        tags=list(tag) if tag else None,
        since=since_date,
    )

    if not notes:
        click.echo("No notes matched the filters.")
        return

    if limit:
        notes = notes[:limit]

    click.echo(f"Found {len(notes)} note(s)")

    processed = {}
    if process or synthesize:
        api_key = get_api_key(cfg)
        if not api_key:
            click.echo("Error: Anthropic API key required. Run: bridge config --anthropic-key KEY", err=True)
            raise SystemExit(1)
        from modules.processor import ClaudeProcessor
        proc = ClaudeProcessor(api_key)

        if synthesize:
            click.echo("Synthesizing with Claude...")
            synthesis = proc.synthesize_notes(notes, topic=topic)
            processed['__synthesis__'] = synthesis
        else:
            click.echo(f"Processing {len(notes)} notes with Claude...")
            with click.progressbar(notes, label='Summarizing') as bar:
                for note in bar:
                    processed[note.title] = proc.summarize_note(note)

    exporter = Exporter(output)

    if synthesize and '__synthesis__' in processed:
        out_file = Path(output) / "synthesis.md"
        out_file.write_text(processed['__synthesis__'], encoding='utf-8')
        exported = [out_file]
        click.echo(f"Synthesis → {out_file}")
    elif merged:
        out_file = exporter.export_merged(notes, processed or None)
        exported = [out_file]
        click.echo(f"Merged → {out_file}")
    else:
        exported = exporter.export_individual(notes, processed or None)
        click.echo(f"Exported {len(exported)} file(s) → {Path(output).absolute()}/")

    exporter.write_manifest(notes, exported)

    if push_drive:
        gdrive_creds = cfg.get('gdrive_credentials')
        if not gdrive_creds:
            click.echo("Error: Google Drive credentials not set. Run: bridge config --gdrive-creds PATH", err=True)
            raise SystemExit(1)
        from modules.gdrive import DriveUploader
        uploader = DriveUploader(gdrive_creds)
        click.echo("Uploading to Google Drive...")
        links = uploader.upload_bundle(exported)
        click.echo("\nGoogle Drive links — add these as sources in NotebookLM:")
        for link in links:
            click.echo(f"  {link}")
    else:
        click.echo(f"\nNext step → NotebookLM:")
        click.echo(f"  notebooklm.google.com → New notebook → Add sources → Upload files")
        click.echo(f"  Files are in: {Path(output).absolute()}/")


# ─── save (NotebookLM → Obsidian) ────────────────────────────────────────────

@cli.command()
@click.option('--title', '-n', required=True, help='Note title')
@click.option('--input', '-i', 'input_file', default=None, help='Text file to import (omit to read from stdin)')
@click.option('--folder', '-f', default='NotebookLM', show_default=True, help='Vault sub-folder to save into')
@click.option('--process/--no-process', default=True, help='Use Claude to format as Obsidian note')
def save(title, input_file, folder, process):
    """Save NotebookLM output back into Obsidian (optionally formatted by Claude)."""
    sys.path.insert(0, str(Path(__file__).parent))
    cfg = load_config()
    vault_path = cfg.get('vault_path', DEFAULT_VAULT)

    if input_file:
        text = Path(input_file).read_text(encoding='utf-8')
    else:
        click.echo("Paste your NotebookLM text, then press Ctrl-D:")
        text = sys.stdin.read()

    if process:
        api_key = get_api_key(cfg)
        if not api_key:
            click.echo("Error: Anthropic API key required.", err=True)
            raise SystemExit(1)
        from modules.processor import ClaudeProcessor
        proc = ClaudeProcessor(api_key)
        out_path = proc.save_to_obsidian(text, title, vault_path, folder)
    else:
        from pathlib import Path as P
        out_dir = P(vault_path) / folder
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c for c in title if c.isalnum() or c in ' -_').strip()
        out_path = str(out_dir / f"{safe}.md")
        P(out_path).write_text(f"# {title}\n\n{text}", encoding='utf-8')

    click.echo(f"Saved → {out_path}")


# ─── list ─────────────────────────────────────────────────────────────────────

@cli.command('list')
@click.option('--folder', '-f', default=None)
@click.option('--tag', '-t', multiple=True)
@click.option('--since', '-s', default=None)
@click.option('--limit', default=20, show_default=True)
def list_notes(folder, tag, since, limit):
    """List notes matching filters (preview before exporting)."""
    sys.path.insert(0, str(Path(__file__).parent))
    from modules.vault import VaultReader

    cfg = load_config()
    vault_path = cfg.get('vault_path', DEFAULT_VAULT)
    reader = VaultReader(vault_path)

    since_date = datetime.strptime(since, '%Y-%m-%d').date() if since else None
    notes = reader.read_notes(
        folder=folder,
        tags=list(tag) if tag else None,
        since=since_date,
    )

    if not notes:
        click.echo("No notes found.")
        return

    click.echo(f"{'Title':<45} {'Folder':<25} {'Modified':<12} Tags")
    click.echo("-" * 100)
    for n in notes[:limit]:
        tags_str = ', '.join(n.tags[:3]) + ('...' if len(n.tags) > 3 else '')
        click.echo(f"{n.title[:44]:<45} {n.folder[:24]:<25} {n.modified.strftime('%Y-%m-%d'):<12} {tags_str}")

    if len(notes) > limit:
        click.echo(f"\n... {len(notes) - limit} more (use --limit to show more)")
    click.echo(f"\nTotal: {len(notes)} note(s)")


if __name__ == '__main__':
    cli()
