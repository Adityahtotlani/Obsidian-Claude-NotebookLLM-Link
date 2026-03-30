import anthropic
from .vault import Note, clean_obsidian_syntax

MODEL = "claude-sonnet-4-6"


class ClaudeProcessor:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def summarize_note(self, note: Note) -> str:
        clean = clean_obsidian_syntax(note.content)
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    f"Summarize this note for use as a NotebookLM source. "
                    f"Keep all key facts, concepts, and insights. "
                    f"Format as clean markdown.\n\n"
                    f"Title: {note.title}\n\n{clean}"
                ),
            }],
        )
        return response.content[0].text

    def synthesize_notes(self, notes: list, topic: str = None) -> str:
        parts = []
        for n in notes:
            clean = clean_obsidian_syntax(n.content)
            parts.append(f"## {n.title}\n\n{clean}")
        combined = "\n\n---\n\n".join(parts)

        topic_str = f" about '{topic}'" if topic else ""
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=8192,
            messages=[{
                "role": "user",
                "content": (
                    f"Synthesize these notes{topic_str} into one coherent document "
                    f"for use as a NotebookLM source. "
                    f"Organize by theme, preserve all key facts, use clear headings.\n\n"
                    f"{combined}"
                ),
            }],
        )
        return response.content[0].text

    def save_to_obsidian(self, text: str, title: str, vault_path: str, folder: str = "NotebookLM") -> str:
        """Take NotebookLM output text and save it as a clean Obsidian note."""
        from pathlib import Path
        from datetime import datetime

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": (
                    f"Convert this text into a well-structured Obsidian markdown note. "
                    f"Add YAML frontmatter with tags and date. "
                    f"Use headers, bullet points, and links where appropriate.\n\n"
                    f"Title: {title}\n\n{text}"
                ),
            }],
        )
        note_content = response.content[0].text

        out_dir = Path(vault_path) / folder
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_title = "".join(c for c in title if c.isalnum() or c in ' -_').strip()
        out_file = out_dir / f"{safe_title}.md"
        out_file.write_text(note_content, encoding='utf-8')
        return str(out_file)
