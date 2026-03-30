import json
from pathlib import Path
from datetime import datetime
from .vault import Note, clean_obsidian_syntax


class Exporter:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_individual(self, notes: list, processed: dict = None) -> list:
        exported = []
        for note in notes:
            content = processed.get(note.title) if processed else clean_obsidian_syntax(note.content)
            safe = "".join(c for c in note.title if c.isalnum() or c in ' -_').strip()
            out = self.output_dir / f"{safe}.md"
            out.write_text(f"# {note.title}\n\n{content}", encoding='utf-8')
            exported.append(out)
        return exported

    def export_merged(self, notes: list, processed: dict = None, filename: str = "merged.md") -> Path:
        header = f"# Knowledge Base Export\n\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\nSources: {len(notes)} notes\n\n---\n\n"
        parts = [header]
        for note in notes:
            content = processed.get(note.title) if processed else clean_obsidian_syntax(note.content)
            parts.append(f"# {note.title}\n\n*Folder: {note.folder} | Modified: {note.modified.strftime('%Y-%m-%d')}*\n\n{content}\n\n---\n\n")
        out = self.output_dir / filename
        out.write_text("".join(parts), encoding='utf-8')
        return out

    def write_manifest(self, notes: list, exported_files: list) -> Path:
        manifest = {
            "exported_at": datetime.now().isoformat(),
            "note_count": len(notes),
            "files": [f.name for f in exported_files],
            "notes": [
                {
                    "title": n.title,
                    "folder": n.folder,
                    "tags": n.tags,
                    "modified": n.modified.isoformat(),
                }
                for n in notes
            ],
        }
        out = self.output_dir / "manifest.json"
        out.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        return out
