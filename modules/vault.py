import re
from pathlib import Path
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Optional


EXCLUDE_FOLDERS = {'.obsidian', '.trash', '.claude', '.git'}


@dataclass
class Note:
    path: Path
    title: str
    content: str
    frontmatter: dict
    tags: list
    modified: datetime
    folder: str


def parse_frontmatter(content: str) -> tuple:
    if not content.startswith('---'):
        return {}, content
    end = content.find('---', 3)
    if end == -1:
        return {}, content
    fm_text = content[3:end].strip()
    body = content[end + 3:].strip()
    fm = {}
    for line in fm_text.split('\n'):
        if ':' in line:
            key, _, value = line.partition(':')
            fm[key.strip()] = value.strip()
    return fm, body


def extract_tags(fm: dict, body: str) -> list:
    raw = fm.get('tags', '')
    if isinstance(raw, list):
        fm_tags = raw
    elif isinstance(raw, str):
        fm_tags = [t.strip() for t in raw.strip('[]').split(',') if t.strip()]
    else:
        fm_tags = []
    inline = re.findall(r'(?<!\S)#([\w/]+)', body)
    return list(set(fm_tags + inline))


def clean_obsidian_syntax(content: str) -> str:
    """Strip Obsidian-specific syntax for clean export."""
    # Remove frontmatter
    if content.startswith('---'):
        end = content.find('---', 3)
        if end != -1:
            content = content[end + 3:].strip()
    # Remove embeds ![[...]]
    content = re.sub(r'!\[\[[^\]]+\]\]', '', content)
    # Resolve wiki links [[target|alias]] -> alias, [[target]] -> target
    content = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', content)
    content = re.sub(r'\[\[([^\]]+)\]\]', r'\1', content)
    # Remove dataview/dataviewjs blocks
    content = re.sub(r'```dataview[\s\S]*?```', '', content, flags=re.IGNORECASE)
    content = re.sub(r'```dataviewjs[\s\S]*?```', '', content, flags=re.IGNORECASE)
    # Remove callout syntax >  [!note] -> keep content
    content = re.sub(r'> \[![^\]]+\]\+?\n', '', content)
    return content.strip()


class VaultReader:
    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)

    def read_notes(
        self,
        folder: Optional[str] = None,
        tags: Optional[list] = None,
        since: Optional[date] = None,
    ) -> list:
        search_root = self.vault_path / folder if folder else self.vault_path
        notes = []

        for md_file in search_root.rglob('*.md'):
            parts = md_file.relative_to(self.vault_path).parts
            if any(p in EXCLUDE_FOLDERS for p in parts):
                continue
            try:
                content = md_file.read_text(encoding='utf-8')
                fm, body = parse_frontmatter(content)
                note_tags = extract_tags(fm, body)
                modified = datetime.fromtimestamp(md_file.stat().st_mtime)

                if since and modified.date() < since:
                    continue
                if tags and not any(t in note_tags for t in tags):
                    continue

                rel_folder = str(md_file.parent.relative_to(self.vault_path))
                notes.append(Note(
                    path=md_file,
                    title=md_file.stem,
                    content=content,
                    frontmatter=fm,
                    tags=note_tags,
                    modified=modified,
                    folder=rel_folder,
                ))
            except Exception:
                continue

        return sorted(notes, key=lambda n: n.modified, reverse=True)
