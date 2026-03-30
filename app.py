#!/usr/bin/env python3
"""
Bridge — Claude · Obsidian · NotebookLM
A macOS dock app for moving content between the three.
"""
import json
import os
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from datetime import date, timedelta
from pathlib import Path

import customtkinter as ctk

sys.path.insert(0, str(Path(__file__).parent))

CONFIG_PATH = Path.home() / '.obsidian-bridge-config.json'
EXPORT_DIR = Path.home() / 'Desktop' / 'NotebookLM-Export'
DEFAULT_VAULT = str(
    Path.home() / 'Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Notes'
)

ctk.set_appearance_mode('system')
ctk.set_default_color_theme('blue')


# ─── helpers ─────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def open_app(name: str):
    subprocess.Popen(['open', '-a', name])


def open_url(url: str):
    webbrowser.open(url)


# ─── main app ────────────────────────────────────────────────────────────────

class BridgeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.vault_path = self.cfg.get('vault_path', DEFAULT_VAULT)
        self._busy = False

        self.title('Bridge')
        self.geometry('560x720')
        self.resizable(False, False)

        self._build_ui()
        self._refresh_note_list()

        # Force window to front on launch
        self.after(100, self._bring_to_front)

    # ── UI ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── top: app launchers ──
        launcher_frame = ctk.CTkFrame(self, fg_color='transparent')
        launcher_frame.pack(fill='x', padx=20, pady=(20, 0))

        ctk.CTkLabel(
            launcher_frame, text='Bridge', font=ctk.CTkFont(size=22, weight='bold')
        ).pack(side='left')

        for label, cmd in [
            ('Claude', self.open_claude),
            ('Obsidian', self.open_obsidian),
            ('NotebookLM', self.open_notebooklm),
        ]:
            ctk.CTkButton(
                launcher_frame, text=f'Open {label}', width=120,
                fg_color='#2D2D2D', hover_color='#444',
                command=cmd,
            ).pack(side='right', padx=4)

        # ── tab view ──
        self.tabs = ctk.CTkTabview(self, height=540)
        self.tabs.pack(fill='both', expand=True, padx=20, pady=12)

        self._build_export_tab(self.tabs.add('Obsidian → NotebookLM'))
        self._build_import_tab(self.tabs.add('NotebookLM → Obsidian'))
        self._build_md_import_tab(self.tabs.add('Import MDs'))
        self._build_claude_tab(self.tabs.add('Ask Claude'))
        self._build_settings_tab(self.tabs.add('Settings'))

        # ── status bar ──
        self.status_var = ctk.StringVar(value='Ready')
        status_bar = ctk.CTkFrame(self, height=28, fg_color='transparent')
        status_bar.pack(fill='x', padx=20, pady=(0, 10))
        self.progress = ctk.CTkProgressBar(status_bar, width=160, height=8)
        self.progress.set(0)
        self.progress.pack(side='left', padx=(0, 10), pady=8)
        ctk.CTkLabel(status_bar, textvariable=self.status_var, font=ctk.CTkFont(size=12)).pack(side='left')

    def _build_export_tab(self, tab):
        # Filter row
        filter_frame = ctk.CTkFrame(tab, fg_color='transparent')
        filter_frame.pack(fill='x', pady=(8, 4))

        ctk.CTkLabel(filter_frame, text='Folder:').pack(side='left', padx=(0, 6))
        self.folder_var = ctk.StringVar(value='')
        self.folder_entry = ctk.CTkEntry(filter_frame, textvariable=self.folder_var, placeholder_text='All folders', width=160)
        self.folder_entry.pack(side='left', padx=(0, 12))

        ctk.CTkLabel(filter_frame, text='Since:').pack(side='left', padx=(0, 6))
        self.since_var = ctk.StringVar(value='7 days')
        ctk.CTkOptionMenu(
            filter_frame, variable=self.since_var,
            values=['Today', '3 days', '7 days', '30 days', 'All time'],
            width=100,
            command=lambda _: self._refresh_note_list(),
        ).pack(side='left')

        ctk.CTkButton(
            filter_frame, text='↺', width=32, command=self._refresh_note_list
        ).pack(side='right')

        # Note list
        list_frame = ctk.CTkFrame(tab)
        list_frame.pack(fill='both', expand=True, pady=8)
        ctk.CTkLabel(list_frame, text='Notes to export:', font=ctk.CTkFont(size=12, weight='bold')).pack(anchor='w', padx=10, pady=(8, 4))

        self.note_listbox = ctk.CTkScrollableFrame(list_frame, height=220)
        self.note_listbox.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.note_vars = []

        # Export buttons
        btn_frame = ctk.CTkFrame(tab, fg_color='transparent')
        btn_frame.pack(fill='x', pady=(4, 0))

        ctk.CTkButton(
            btn_frame, text='Export Selected (Raw)',
            command=self.export_selected,
        ).pack(side='left', padx=(0, 8), fill='x', expand=True)

        ctk.CTkButton(
            btn_frame, text='Export + Summarize with Claude',
            command=self.export_summarize,
            fg_color='#1a6b3c', hover_color='#2a8a52',
        ).pack(side='left', fill='x', expand=True)

        ctk.CTkButton(
            tab, text='Open Export Folder in Finder',
            fg_color='transparent', border_width=1,
            text_color=('gray20', 'gray80'),
            command=self.open_export_folder,
        ).pack(fill='x', pady=(8, 0))

    def _build_import_tab(self, tab):
        ctk.CTkLabel(
            tab, text='Paste text from NotebookLM:',
            font=ctk.CTkFont(size=13, weight='bold'),
        ).pack(anchor='w', pady=(8, 4))

        self.import_text = ctk.CTkTextbox(tab, height=280, wrap='word')
        self.import_text.pack(fill='both', expand=True)

        ctk.CTkButton(
            tab, text='Paste from Clipboard',
            fg_color='transparent', border_width=1,
            text_color=('gray20', 'gray80'),
            command=self._paste_import,
        ).pack(fill='x', pady=(8, 0))

        title_frame = ctk.CTkFrame(tab, fg_color='transparent')
        title_frame.pack(fill='x', pady=8)
        ctk.CTkLabel(title_frame, text='Note title:').pack(side='left', padx=(0, 8))
        self.import_title = ctk.CTkEntry(title_frame, placeholder_text='e.g. History Summary', width=260)
        self.import_title.pack(side='left')

        ctk.CTkLabel(title_frame, text='Folder:').pack(side='left', padx=(12, 6))
        self.import_folder = ctk.CTkEntry(title_frame, placeholder_text='NotebookLM', width=120)
        self.import_folder.pack(side='left')

        btn_frame = ctk.CTkFrame(tab, fg_color='transparent')
        btn_frame.pack(fill='x')

        ctk.CTkButton(
            btn_frame, text='Save to Obsidian (Raw)',
            command=lambda: self._do_import(format_with_claude=False),
        ).pack(side='left', padx=(0, 8), fill='x', expand=True)

        ctk.CTkButton(
            btn_frame, text='Save + Format with Claude',
            command=lambda: self._do_import(format_with_claude=True),
            fg_color='#1a6b3c', hover_color='#2a8a52',
        ).pack(side='left', fill='x', expand=True)

    def _build_md_import_tab(self, tab):
        ctk.CTkLabel(
            tab, text='Import Markdown files into your vault',
            font=ctk.CTkFont(size=13, weight='bold'),
        ).pack(anchor='w', pady=(8, 4))

        # Pick files / folder buttons
        pick_frame = ctk.CTkFrame(tab, fg_color='transparent')
        pick_frame.pack(fill='x', pady=(0, 6))
        ctk.CTkButton(
            pick_frame, text='Pick Files…', width=130,
            command=self._pick_md_files,
        ).pack(side='left', padx=(0, 8))
        ctk.CTkButton(
            pick_frame, text='Pick Folder…', width=130,
            command=self._pick_md_folder,
        ).pack(side='left')
        self.md_count_label = ctk.CTkLabel(
            pick_frame, text='No files selected',
            font=ctk.CTkFont(size=12), text_color='gray60',
        )
        self.md_count_label.pack(side='left', padx=12)

        # File list
        list_frame = ctk.CTkFrame(tab)
        list_frame.pack(fill='both', expand=True, pady=(0, 8))
        self.md_listbox = ctk.CTkScrollableFrame(list_frame, height=220)
        self.md_listbox.pack(fill='both', expand=True, padx=8, pady=8)
        self._md_files = []

        # Destination folder
        dest_frame = ctk.CTkFrame(tab, fg_color='transparent')
        dest_frame.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(dest_frame, text='Save to folder:', width=110, anchor='w').pack(side='left')
        self.md_dest_entry = ctk.CTkEntry(dest_frame, placeholder_text='e.g. Claude Chats', width=200)
        self.md_dest_entry.insert(0, 'Claude Chats')
        self.md_dest_entry.pack(side='left', padx=(0, 12))
        self.md_clean_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            dest_frame, text='Clean up with Claude',
            variable=self.md_clean_var,
        ).pack(side='left')

        # Import button
        ctk.CTkButton(
            tab, text='Import into Vault',
            fg_color='#1a6b3c', hover_color='#2a8a52',
            command=self._do_md_import,
        ).pack(fill='x')

    def _pick_md_files(self):
        import tkinter.filedialog as fd
        paths = fd.askopenfilenames(
            title='Select Markdown files',
            filetypes=[('Markdown', '*.md'), ('All files', '*.*')],
        )
        if paths:
            self._md_files = [Path(p) for p in paths]
            self._populate_md_list()

    def _pick_md_folder(self):
        import tkinter.filedialog as fd
        folder = fd.askdirectory(title='Select folder containing Markdown files')
        if folder:
            self._md_files = list(Path(folder).rglob('*.md'))
            self._populate_md_list()

    def _populate_md_list(self):
        for w in self.md_listbox.winfo_children():
            w.destroy()
        for f in self._md_files:
            row = ctk.CTkFrame(self.md_listbox, fg_color='transparent')
            row.pack(fill='x', pady=1)
            ctk.CTkLabel(
                row, text=f.name,
                font=ctk.CTkFont(size=12), anchor='w',
            ).pack(side='left', fill='x', expand=True)
            size_kb = round(f.stat().st_size / 1024, 1)
            ctk.CTkLabel(
                row, text=f'{size_kb} KB',
                font=ctk.CTkFont(size=11), text_color='gray60',
            ).pack(side='right', padx=4)
        n = len(self._md_files)
        self.md_count_label.configure(text=f'{n} file{"s" if n != 1 else ""} selected')

    def _do_md_import(self):
        if not self._md_files:
            self._set_status('No files selected')
            return
        dest_folder = self.md_dest_entry.get().strip() or 'Claude Chats'
        clean = self.md_clean_var.get()
        if clean and not self._get_api_key():
            self._show_no_key()
            return
        if self._busy:
            return
        self._busy = True
        self._set_status(f'Importing {len(self._md_files)} files...')
        self.progress.configure(mode='indeterminate')
        self.progress.start()

        def worker():
            try:
                out_dir = Path(self.vault_path) / dest_folder
                out_dir.mkdir(parents=True, exist_ok=True)
                imported = []

                if clean:
                    import anthropic
                    client = anthropic.Anthropic(api_key=self._get_api_key())

                for i, src in enumerate(self._md_files):
                    self.after(0, lambda i=i: self._set_status(
                        f'Importing {i+1}/{len(self._md_files)}: {src.name}'
                    ))
                    content = src.read_text(encoding='utf-8', errors='replace')

                    if clean:
                        resp = client.messages.create(
                            model='claude-sonnet-4-6',
                            max_tokens=4096,
                            messages=[{
                                'role': 'user',
                                'content': (
                                    'Clean up this Claude-generated markdown file for Obsidian. '
                                    'Add YAML frontmatter (tags, date). '
                                    'Fix any formatting issues. Keep all content.\n\n'
                                    f'{content}'
                                ),
                            }],
                        )
                        content = resp.content[0].text

                    dest_file = out_dir / src.name
                    # Avoid overwriting: add suffix if exists
                    if dest_file.exists():
                        stem = src.stem
                        suffix = src.suffix
                        counter = 1
                        while dest_file.exists():
                            dest_file = out_dir / f'{stem} ({counter}){suffix}'
                            counter += 1

                    dest_file.write_text(content, encoding='utf-8')
                    imported.append(dest_file)

                # Open vault folder in Obsidian
                encoded = urllib.parse.quote(dest_folder)
                open_url(f'obsidian://open?vault=Obsidian%20Notes')
                self.after(0, lambda: self._md_import_done(len(imported), dest_folder))
            except Exception as e:
                self.after(0, lambda: self._set_status(f'Error: {e}'))
                self._busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _md_import_done(self, count, folder):
        self.progress.stop()
        self.progress.configure(mode='determinate')
        self.progress.set(1)
        self._set_status(f'Imported {count} file{"s" if count != 1 else ""} → {folder}/')
        self._busy = False
        # Show in Finder too
        subprocess.Popen(['open', str(Path(self.vault_path) / folder)])

    def _build_claude_tab(self, tab):
        ctk.CTkLabel(
            tab, text='Ask Claude about your notes:',
            font=ctk.CTkFont(size=13, weight='bold'),
        ).pack(anchor='w', pady=(8, 4))

        self.claude_input = ctk.CTkTextbox(tab, height=120, wrap='word')
        self.claude_input.pack(fill='x')
        self.claude_input.insert('0.0', 'e.g. Summarize my IB History notes as bullet points')

        opts_frame = ctk.CTkFrame(tab, fg_color='transparent')
        opts_frame.pack(fill='x', pady=8)

        ctk.CTkLabel(opts_frame, text='Context folder:').pack(side='left', padx=(0, 6))
        self.claude_folder = ctk.CTkEntry(opts_frame, placeholder_text='All vault', width=160)
        self.claude_folder.pack(side='left', padx=(0, 12))

        ctk.CTkButton(
            opts_frame, text='Ask Claude',
            command=self._ask_claude, width=120,
        ).pack(side='right')

        ctk.CTkLabel(tab, text='Response:', font=ctk.CTkFont(size=12, weight='bold')).pack(anchor='w', pady=(4, 2))

        self.claude_output = ctk.CTkTextbox(tab, height=220, wrap='word', state='disabled')
        self.claude_output.pack(fill='both', expand=True)

        btn_frame = ctk.CTkFrame(tab, fg_color='transparent')
        btn_frame.pack(fill='x', pady=(6, 0))
        ctk.CTkButton(
            btn_frame, text='Copy Response',
            command=self._copy_claude_response,
            fg_color='transparent', border_width=1,
            text_color=('gray20', 'gray80'),
        ).pack(side='left', padx=(0, 8))
        ctk.CTkButton(
            btn_frame, text='Save Response to Obsidian',
            command=self._save_claude_to_obsidian,
        ).pack(side='left')

    def _build_settings_tab(self, tab):
        def row(label, widget_builder):
            f = ctk.CTkFrame(tab, fg_color='transparent')
            f.pack(fill='x', pady=6)
            ctk.CTkLabel(f, text=label, width=140, anchor='w').pack(side='left')
            widget_builder(f).pack(side='left', fill='x', expand=True)

        ctk.CTkLabel(tab, text='Settings', font=ctk.CTkFont(size=16, weight='bold')).pack(anchor='w', pady=(8, 12))

        # API key
        api_frame = ctk.CTkFrame(tab, fg_color='transparent')
        api_frame.pack(fill='x', pady=6)
        ctk.CTkLabel(api_frame, text='Anthropic API Key:', width=140, anchor='w').pack(side='left')
        self.api_key_entry = ctk.CTkEntry(api_frame, show='*', placeholder_text='sk-ant-...')
        self.api_key_entry.pack(side='left', fill='x', expand=True)
        if self.cfg.get('anthropic_key'):
            self.api_key_entry.insert(0, self.cfg['anthropic_key'])

        # Vault path
        vault_frame = ctk.CTkFrame(tab, fg_color='transparent')
        vault_frame.pack(fill='x', pady=6)
        ctk.CTkLabel(vault_frame, text='Vault Path:', width=140, anchor='w').pack(side='left')
        self.vault_entry = ctk.CTkEntry(vault_frame, placeholder_text=DEFAULT_VAULT)
        self.vault_entry.insert(0, self.vault_path)
        self.vault_entry.pack(side='left', fill='x', expand=True)

        # Save button
        ctk.CTkButton(tab, text='Save Settings', command=self._save_settings).pack(anchor='w', pady=(16, 0))

        # Info
        info = ctk.CTkLabel(
            tab,
            text='API key is stored in ~/.obsidian-bridge-config.json',
            font=ctk.CTkFont(size=11), text_color='gray60',
        )
        info.pack(anchor='w', pady=(4, 0))

    # ── note list ────────────────────────────────────────────────────────

    def _refresh_note_list(self):
        for widget in self.note_listbox.winfo_children():
            widget.destroy()
        self.note_vars = []
        self._notes = []

        def worker():
            try:
                from modules.vault import VaultReader
                reader = VaultReader(self.vault_path)
                since_map = {
                    'Today': 0, '3 days': 3, '7 days': 7,
                    '30 days': 30, 'All time': None,
                }
                days = since_map.get(self.since_var.get(), 7)
                since_date = date.today() - timedelta(days=days) if days is not None else None
                folder = self.folder_var.get().strip() or None
                notes = reader.read_notes(folder=folder, since=since_date)
                self._notes = notes
                self.after(0, lambda: self._populate_note_list(notes))
            except Exception as e:
                self.after(0, lambda: self._set_status(f'Error: {e}'))

        threading.Thread(target=worker, daemon=True).start()

    def _populate_note_list(self, notes):
        self.note_vars = []
        for note in notes:
            var = ctk.BooleanVar(value=True)
            self.note_vars.append((var, note))
            row = ctk.CTkFrame(self.note_listbox, fg_color='transparent')
            row.pack(fill='x', pady=1)
            ctk.CTkCheckBox(
                row, text=f"{note.title}  ({note.folder})",
                variable=var, font=ctk.CTkFont(size=12),
            ).pack(side='left')
            ctk.CTkLabel(
                row, text=note.modified.strftime('%b %d'),
                font=ctk.CTkFont(size=11), text_color='gray60',
            ).pack(side='right', padx=4)

        self._set_status(f'{len(notes)} notes loaded')

    # ── export ───────────────────────────────────────────────────────────

    def _selected_notes(self):
        return [note for var, note in self.note_vars if var.get()]

    def export_selected(self):
        self._run_export(summarize=False)

    def export_summarize(self):
        if not self._get_api_key():
            self._show_no_key()
            return
        self._run_export(summarize=True)

    def _run_export(self, summarize=False):
        notes = self._selected_notes()
        if not notes:
            self._set_status('No notes selected')
            return
        if self._busy:
            return
        self._busy = True
        self._set_status(f'Exporting {len(notes)} notes...')
        self.progress.configure(mode='indeterminate')
        self.progress.start()

        def worker():
            try:
                from modules.exporter import Exporter
                EXPORT_DIR.mkdir(parents=True, exist_ok=True)
                processed = {}
                if summarize:
                    from modules.processor import ClaudeProcessor
                    proc = ClaudeProcessor(self._get_api_key())
                    for i, note in enumerate(notes):
                        self.after(0, lambda i=i: self._set_status(f'Summarizing {i+1}/{len(notes)}...'))
                        processed[note.title] = proc.summarize_note(note)

                exporter = Exporter(str(EXPORT_DIR))
                exported = exporter.export_individual(notes, processed or None)
                exporter.write_manifest(notes, exported)

                self.after(0, lambda: self._export_done(len(exported)))
            except Exception as e:
                self.after(0, lambda: self._set_status(f'Error: {e}'))
                self._busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _export_done(self, count):
        self.progress.stop()
        self.progress.configure(mode='determinate')
        self.progress.set(1)
        self._set_status(f'Exported {count} notes to Desktop/NotebookLM-Export')
        self._busy = False
        subprocess.Popen(['open', str(EXPORT_DIR)])

    def open_export_folder(self):
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(['open', str(EXPORT_DIR)])

    # ── import ───────────────────────────────────────────────────────────

    def _paste_import(self):
        try:
            import pyperclip
            text = pyperclip.paste()
        except Exception:
            text = self.clipboard_get()
        self.import_text.delete('0.0', 'end')
        self.import_text.insert('0.0', text)

    def _do_import(self, format_with_claude=False):
        text = self.import_text.get('0.0', 'end').strip()
        if not text:
            self._set_status('No text to save')
            return
        title = self.import_title.get().strip() or 'NotebookLM Note'
        folder = self.import_folder.get().strip() or 'NotebookLM'

        if format_with_claude and not self._get_api_key():
            self._show_no_key()
            return
        if self._busy:
            return
        self._busy = True
        self._set_status(f'Saving "{title}" to Obsidian...')
        self.progress.configure(mode='indeterminate')
        self.progress.start()

        def worker():
            try:
                if format_with_claude:
                    from modules.processor import ClaudeProcessor
                    proc = ClaudeProcessor(self._get_api_key())
                    out_path = proc.save_to_obsidian(text, title, self.vault_path, folder)
                else:
                    out_dir = Path(self.vault_path) / folder
                    out_dir.mkdir(parents=True, exist_ok=True)
                    safe = "".join(c for c in title if c.isalnum() or c in ' -_').strip()
                    out_path = str(out_dir / f"{safe}.md")
                    Path(out_path).write_text(f"# {title}\n\n{text}", encoding='utf-8')

                rel = Path(out_path).relative_to(self.vault_path)
                encoded = urllib.parse.quote(str(rel))
                open_url(f"obsidian://open?path={encoded}")
                self.after(0, lambda: self._import_done(title))
            except Exception as e:
                self.after(0, lambda: self._set_status(f'Error: {e}'))
                self._busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _import_done(self, title):
        self.progress.stop()
        self.progress.configure(mode='determinate')
        self.progress.set(1)
        self._set_status(f'Saved "{title}" and opened in Obsidian')
        self._busy = False

    # ── claude tab ───────────────────────────────────────────────────────

    def _ask_claude(self):
        if not self._get_api_key():
            self._show_no_key()
            return
        prompt = self.claude_input.get('0.0', 'end').strip()
        if not prompt:
            return
        folder = self.claude_folder.get().strip() or None
        if self._busy:
            return
        self._busy = True
        self._set_status('Asking Claude...')
        self.progress.configure(mode='indeterminate')
        self.progress.start()

        def worker():
            try:
                from modules.vault import VaultReader
                reader = VaultReader(self.vault_path)
                notes = reader.read_notes(folder=folder)[:20]

                from modules.vault import clean_obsidian_syntax
                context = '\n\n---\n\n'.join(
                    f"## {n.title}\n\n{clean_obsidian_syntax(n.content)}" for n in notes
                )
                import anthropic
                client = anthropic.Anthropic(api_key=self._get_api_key())
                resp = client.messages.create(
                    model='claude-sonnet-4-6',
                    max_tokens=2048,
                    messages=[{
                        'role': 'user',
                        'content': (
                            f"You have access to the following Obsidian notes:\n\n{context}\n\n"
                            f"---\n\nUser question: {prompt}"
                        ),
                    }],
                )
                answer = resp.content[0].text
                self.after(0, lambda: self._show_claude_response(answer))
            except Exception as e:
                self.after(0, lambda: self._set_status(f'Error: {e}'))
                self._busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _show_claude_response(self, text):
        self.progress.stop()
        self.progress.configure(mode='determinate')
        self.progress.set(1)
        self.claude_output.configure(state='normal')
        self.claude_output.delete('0.0', 'end')
        self.claude_output.insert('0.0', text)
        self.claude_output.configure(state='disabled')
        self._set_status('Claude responded')
        self._busy = False
        self._last_claude_response = text

    def _copy_claude_response(self):
        text = self.claude_output.get('0.0', 'end').strip()
        if text:
            try:
                import pyperclip
                pyperclip.copy(text)
            except Exception:
                self.clipboard_clear()
                self.clipboard_append(text)
            self._set_status('Response copied to clipboard')

    def _save_claude_to_obsidian(self):
        text = getattr(self, '_last_claude_response', '').strip()
        if not text:
            self._set_status('No response to save')
            return
        out_dir = Path(self.vault_path) / 'Claude'
        out_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        filename = f"Claude Response {datetime.now().strftime('%Y-%m-%d %H%M')}.md"
        out_file = out_dir / filename
        prompt = self.claude_input.get('0.0', 'end').strip()
        out_file.write_text(
            f"---\ntags: claude\ndate: {date.today()}\n---\n\n"
            f"# Claude Response\n\n**Prompt:** {prompt}\n\n---\n\n{text}",
            encoding='utf-8'
        )
        rel = out_file.relative_to(self.vault_path)
        encoded = urllib.parse.quote(str(rel))
        open_url(f"obsidian://open?path={encoded}")
        self._set_status(f'Saved to Obsidian: Claude/{filename}')

    # ── app launchers ────────────────────────────────────────────────────

    def open_claude(self):
        try:
            open_app('Claude')
        except Exception:
            open_url('https://claude.ai')

    def open_obsidian(self):
        try:
            open_app('Obsidian')
        except Exception:
            open_url('obsidian://')

    def open_notebooklm(self):
        open_url('https://notebooklm.google.com')

    # ── settings ─────────────────────────────────────────────────────────

    def _save_settings(self):
        key = self.api_key_entry.get().strip()
        vault = self.vault_entry.get().strip()
        if key:
            self.cfg['anthropic_key'] = key
        if vault:
            self.cfg['vault_path'] = vault
            self.vault_path = vault
        save_config(self.cfg)
        self._set_status('Settings saved')

    def _get_api_key(self) -> str:
        return self.cfg.get('anthropic_key') or os.environ.get('ANTHROPIC_API_KEY', '')

    def _show_no_key(self):
        self._set_status('Add your Anthropic API key in Settings tab')
        self.tabs.set('Settings')

    # ── status ───────────────────────────────────────────────────────────

    def _bring_to_front(self):
        self.lift()
        self.focus_force()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        # Also activate via AppleScript for macOS dock focus
        subprocess.Popen([
            'osascript', '-e',
            'tell application "System Events" to set frontmost of first process whose unix id is '
            + str(os.getpid()) + ' to true'
        ])

    def _set_status(self, msg: str):
        self.status_var.set(msg)


if __name__ == '__main__':
    app = BridgeApp()
    app.mainloop()
