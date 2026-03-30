#!/usr/bin/env python3
"""
Obsidian ↔ Claude ↔ NotebookLM Menu Bar App
Sits in your macOS status bar for one-click transfers.
"""
import json
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import rumps
import pyperclip

sys.path.insert(0, str(Path(__file__).parent))
from modules.vault import VaultReader
from modules.exporter import Exporter
from modules.processor import ClaudeProcessor

CONFIG_PATH = Path.home() / '.obsidian-bridge-config.json'
EXPORT_DIR = Path.home() / 'Desktop' / 'NotebookLM-Export'
DEFAULT_VAULT = str(Path.home() / 'Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Notes')


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def open_app(name: str):
    subprocess.Popen(['open', '-a', name])


def open_url(url: str):
    webbrowser.open(url)


def notify(title: str, subtitle: str, message: str = ''):
    rumps.notification(title, subtitle, message, sound=True)


class BridgeApp(rumps.App):
    def __init__(self):
        super().__init__(
            name='Bridge',
            title='⟁',
            quit_button=None,
        )
        self.cfg = load_config()
        self.vault_path = self.cfg.get('vault_path', DEFAULT_VAULT)
        self._build_menu()

    def _build_menu(self):
        self.menu = [
            rumps.MenuItem('Open Apps', callback=None),
            rumps.MenuItem('  Open Claude', callback=self.open_claude),
            rumps.MenuItem('  Open Obsidian', callback=self.open_obsidian),
            rumps.MenuItem('  Open NotebookLM', callback=self.open_notebooklm),
            None,
            rumps.MenuItem('Obsidian → NotebookLM', callback=None),
            rumps.MenuItem('  Export Recent (7 days)', callback=self.export_recent),
            rumps.MenuItem('  Export All Notes', callback=self.export_all),
            rumps.MenuItem('  Export + Summarize with Claude', callback=self.export_summarize),
            rumps.MenuItem('  Open Last Export in Finder', callback=self.open_export_folder),
            None,
            rumps.MenuItem('NotebookLM → Obsidian', callback=None),
            rumps.MenuItem('  Save Clipboard Note', callback=self.save_clipboard),
            rumps.MenuItem('  Save Clipboard + Format with Claude', callback=self.save_clipboard_formatted),
            None,
            rumps.MenuItem('Quick Actions', callback=None),
            rumps.MenuItem('  Summarize Clipboard with Claude', callback=self.summarize_clipboard),
            rumps.MenuItem('  Copy Last Export Path', callback=self.copy_export_path),
            None,
            rumps.MenuItem('Settings', callback=self.open_settings),
            rumps.MenuItem('Quit', callback=rumps.quit_application),
        ]

    # ── Open Apps ─────────────────────────────────────────────────────────

    def open_claude(self, _):
        try:
            open_app('Claude')
        except Exception:
            open_url('https://claude.ai')

    def open_obsidian(self, _):
        try:
            open_app('Obsidian')
        except Exception:
            open_url('obsidian://')

    def open_notebooklm(self, _):
        open_url('https://notebooklm.google.com')

    # ── Obsidian → NotebookLM ──────────────────────────────────────────────

    def export_recent(self, _):
        self._run_export(days=7, label='Recent (7 days)')

    def export_all(self, _):
        self._run_export(days=None, label='All notes')

    def export_summarize(self, _):
        api_key = self.cfg.get('anthropic_key') or os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key:
            rumps.alert('API Key Missing', 'Set your Anthropic API key in Settings.')
            return
        self._run_export(days=7, label='Recent + Summarized', summarize=True, api_key=api_key)

    def _run_export(self, days=None, label='Notes', summarize=False, api_key=None):
        self.title = '⟳'
        notify('Bridge', f'Exporting {label}...', 'Processing your vault')

        def worker():
            try:
                from datetime import date, timedelta
                reader = VaultReader(self.vault_path)
                since = date.today() - timedelta(days=days) if days else None
                notes = reader.read_notes(since=since)

                if not notes:
                    notify('Bridge', 'No notes found', f'No notes modified in last {days} days' if days else '')
                    self.title = '⟁'
                    return

                processed = {}
                if summarize and api_key:
                    proc = ClaudeProcessor(api_key)
                    for note in notes:
                        processed[note.title] = proc.summarize_note(note)

                EXPORT_DIR.mkdir(parents=True, exist_ok=True)
                exporter = Exporter(str(EXPORT_DIR))
                exported = exporter.export_individual(notes, processed or None)
                exporter.write_manifest(notes, exported)

                notify(
                    'Bridge — Export Ready',
                    f'{len(exported)} notes exported',
                    'Open NotebookLM and upload from Desktop/NotebookLM-Export'
                )
                self.title = '⟁'

            except Exception as e:
                notify('Bridge — Error', str(e))
                self.title = '⟁'

        threading.Thread(target=worker, daemon=True).start()

    def open_export_folder(self, _):
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(['open', str(EXPORT_DIR)])

    # ── NotebookLM → Obsidian ──────────────────────────────────────────────

    def save_clipboard(self, _):
        text = pyperclip.paste().strip()
        if not text:
            rumps.alert('Clipboard Empty', 'Copy some text from NotebookLM first.')
            return
        response = rumps.Window(
            title='Save to Obsidian',
            message='Note title:',
            default_text='NotebookLM Note',
            ok='Save',
            cancel='Cancel',
            dimensions=(300, 20),
        ).run()
        if not response.clicked:
            return
        title = response.text.strip() or 'NotebookLM Note'
        self._save_note(text, title, format_with_claude=False)

    def save_clipboard_formatted(self, _):
        api_key = self.cfg.get('anthropic_key') or os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key:
            rumps.alert('API Key Missing', 'Set your Anthropic API key in Settings.')
            return
        text = pyperclip.paste().strip()
        if not text:
            rumps.alert('Clipboard Empty', 'Copy some text from NotebookLM first.')
            return
        response = rumps.Window(
            title='Save to Obsidian',
            message='Note title:',
            default_text='NotebookLM Note',
            ok='Save',
            cancel='Cancel',
            dimensions=(300, 20),
        ).run()
        if not response.clicked:
            return
        title = response.text.strip() or 'NotebookLM Note'
        self._save_note(text, title, format_with_claude=True, api_key=api_key)

    def _save_note(self, text, title, format_with_claude=False, api_key=None):
        self.title = '⟳'
        notify('Bridge', f'Saving "{title}" to Obsidian...', '')

        def worker():
            try:
                if format_with_claude and api_key:
                    proc = ClaudeProcessor(api_key)
                    path = proc.save_to_obsidian(text, title, self.vault_path, 'NotebookLM')
                else:
                    vault = Path(self.vault_path) / 'NotebookLM'
                    vault.mkdir(parents=True, exist_ok=True)
                    safe = "".join(c for c in title if c.isalnum() or c in ' -_').strip()
                    path = str(vault / f"{safe}.md")
                    Path(path).write_text(f"# {title}\n\n{text}", encoding='utf-8')

                # Open the note in Obsidian via URL scheme
                import urllib.parse
                rel = Path(path).relative_to(self.vault_path)
                encoded = urllib.parse.quote(str(rel))
                open_url(f"obsidian://open?path={encoded}")

                notify('Bridge', f'"{title}" saved to Obsidian', 'Opening in Obsidian...')
                self.title = '⟁'
            except Exception as e:
                notify('Bridge — Error', str(e))
                self.title = '⟁'

        threading.Thread(target=worker, daemon=True).start()

    # ── Quick Actions ──────────────────────────────────────────────────────

    def summarize_clipboard(self, _):
        api_key = self.cfg.get('anthropic_key') or os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key:
            rumps.alert('API Key Missing', 'Set your Anthropic API key in Settings.')
            return
        text = pyperclip.paste().strip()
        if not text:
            rumps.alert('Clipboard Empty', 'Copy some text first.')
            return

        self.title = '⟳'
        notify('Bridge', 'Summarizing with Claude...', '')

        def worker():
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                resp = client.messages.create(
                    model='claude-sonnet-4-6',
                    max_tokens=1024,
                    messages=[{
                        'role': 'user',
                        'content': f'Summarize this concisely as bullet points:\n\n{text}'
                    }],
                )
                summary = resp.content[0].text
                pyperclip.copy(summary)
                notify('Bridge', 'Summary copied to clipboard', 'Paste into NotebookLM or Obsidian')
                self.title = '⟁'
            except Exception as e:
                notify('Bridge — Error', str(e))
                self.title = '⟁'

        threading.Thread(target=worker, daemon=True).start()

    def copy_export_path(self, _):
        pyperclip.copy(str(EXPORT_DIR))
        notify('Bridge', 'Export path copied', str(EXPORT_DIR))

    # ── Settings ───────────────────────────────────────────────────────────

    def open_settings(self, _):
        response = rumps.Window(
            title='Bridge Settings',
            message='Anthropic API Key:',
            default_text=self.cfg.get('anthropic_key', ''),
            ok='Save',
            cancel='Cancel',
            dimensions=(400, 20),
        ).run()
        if response.clicked and response.text.strip():
            self.cfg['anthropic_key'] = response.text.strip()
            CONFIG_PATH.write_text(json.dumps(self.cfg, indent=2))
            notify('Bridge', 'Settings saved', '')


if __name__ == '__main__':
    BridgeApp().run()
