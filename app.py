#!/usr/bin/env python3
"""
Bridge — Claude · Obsidian · NotebookLM
macOS dock app for moving content between the three.
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

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont, QPalette, QIcon, QPixmap, QPainter, QBrush
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QLineEdit, QTextEdit, QCheckBox,
    QScrollArea, QFrame, QComboBox, QFileDialog, QProgressBar,
    QSizePolicy, QListWidget, QListWidgetItem, QSplitter, QMessageBox,
)

sys.path.insert(0, str(Path(__file__).parent))

CONFIG_PATH = Path.home() / '.obsidian-bridge-config.json'
EXPORT_DIR = Path.home() / 'Desktop' / 'NotebookLM-Export'
DEFAULT_VAULT = str(
    Path.home() / 'Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Notes'
)

# ── palette ──────────────────────────────────────────────────────────────────
PURPLE = '#7C3AED'
GREEN  = '#059669'
DARK   = '#1E1E2E'
CARD   = '#2A2A3E'
TEXT   = '#E2E8F0'
MUTED  = '#94A3B8'
BORDER = '#3F3F5A'


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def open_url(url: str):
    webbrowser.open(url)


def open_app(name: str):
    subprocess.Popen(['open', '-a', name])


# ── styled widgets ────────────────────────────────────────────────────────────

def btn(text, color=PURPLE, width=None):
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    w = f'width:{width}px;' if width else 'min-width:100px;'
    b.setStyleSheet(f"""
        QPushButton {{
            background:{color}; color:#fff; border:none;
            border-radius:8px; padding:8px 16px; font-size:13px; font-weight:600;
            {w}
        }}
        QPushButton:hover {{ background:{color}dd; }}
        QPushButton:pressed {{ background:{color}aa; }}
        QPushButton:disabled {{ background:#444; color:#888; }}
    """)
    return b


def ghost_btn(text, width=None):
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    w = f'width:{width}px;' if width else 'min-width:100px;'
    b.setStyleSheet(f"""
        QPushButton {{
            background:transparent; color:{MUTED}; border:1px solid {BORDER};
            border-radius:8px; padding:7px 14px; font-size:12px;
            {w}
        }}
        QPushButton:hover {{ color:{TEXT}; border-color:#6B6B8A; }}
    """)
    return b


def label(text, size=13, bold=False, color=TEXT):
    l = QLabel(text)
    w = 700 if bold else 400
    l.setStyleSheet(f'color:{color}; font-size:{size}px; font-weight:{w};')
    return l


def entry(placeholder='', password=False):
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    if password:
        e.setEchoMode(QLineEdit.EchoMode.Password)
    e.setStyleSheet(f"""
        QLineEdit {{
            background:{CARD}; color:{TEXT}; border:1px solid {BORDER};
            border-radius:6px; padding:7px 10px; font-size:13px;
        }}
        QLineEdit:focus {{ border-color:{PURPLE}; }}
    """)
    return e


def card(layout_type='v'):
    f = QFrame()
    f.setStyleSheet(f'background:{CARD}; border-radius:10px; border:1px solid {BORDER};')
    lay = QVBoxLayout(f) if layout_type == 'v' else QHBoxLayout(f)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    return f, lay


def separator():
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f'color:{BORDER};')
    return line


# ── worker thread ─────────────────────────────────────────────────────────────

class Worker(QThread):
    status = pyqtSignal(str)
    done   = pyqtSignal(object)
    error  = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._fn(self.status.emit, *self._args, **self._kwargs)
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ── main window ───────────────────────────────────────────────────────────────

class BridgeApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.vault_path = self.cfg.get('vault_path', DEFAULT_VAULT)
        self._notes = []
        self._md_files = []
        self._last_claude = ''
        self._worker = None

        self.setWindowTitle('Bridge')
        self.setFixedSize(600, 700)
        self.setStyleSheet(f'background:{DARK}; color:{TEXT};')

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        root.addWidget(self._build_header())
        root.addWidget(self._build_tabs(), stretch=1)
        root.addWidget(self._build_statusbar())

        self._refresh_notes()

    # ── header ────────────────────────────────────────────────────────────

    def _build_header(self):
        f = QWidget()
        lay = QHBoxLayout(f)
        lay.setContentsMargins(0, 0, 0, 0)

        title = QLabel('Bridge')
        title.setStyleSheet(f'color:{TEXT}; font-size:20px; font-weight:700;')
        lay.addWidget(title)
        lay.addStretch()

        for text, fn in [('Claude', self._open_claude),
                          ('Obsidian', self._open_obsidian),
                          ('NotebookLM', self._open_notebooklm)]:
            b = ghost_btn(f'Open {text}', width=120)
            b.clicked.connect(fn)
            lay.addWidget(b)

        return f

    # ── tabs ──────────────────────────────────────────────────────────────

    def _build_tabs(self):
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border:1px solid {BORDER}; border-radius:10px; background:{CARD}; }}
            QTabBar::tab {{
                background:{DARK}; color:{MUTED}; padding:8px 16px;
                border-radius:6px; margin-right:4px; font-size:12px;
            }}
            QTabBar::tab:selected {{ background:{PURPLE}; color:#fff; font-weight:600; }}
            QTabBar::tab:hover {{ color:{TEXT}; }}
        """)
        tabs.addTab(self._build_export_tab(), 'Obsidian → NotebookLM')
        tabs.addTab(self._build_import_tab(), 'NotebookLM → Obsidian')
        tabs.addTab(self._build_md_tab(),     'Import MDs')
        tabs.addTab(self._build_claude_tab(), 'Ask Claude')
        tabs.addTab(self._build_settings_tab(), 'Settings')
        return tabs

    # ── export tab ────────────────────────────────────────────────────────

    def _build_export_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        # Filters
        filt, frow = card('h')
        filt.setStyleSheet(f'background:{DARK}; border:none;')

        frow.addWidget(label('Folder:', 12, color=MUTED))
        self.exp_folder = entry('All folders')
        self.exp_folder.setFixedWidth(160)
        frow.addWidget(self.exp_folder)

        frow.addWidget(label('Since:', 12, color=MUTED))
        self.exp_since = QComboBox()
        self.exp_since.addItems(['Today', '3 days', '7 days', '30 days', 'All time'])
        self.exp_since.setCurrentText('7 days')
        self.exp_since.setStyleSheet(f"""
            QComboBox {{ background:{CARD}; color:{TEXT}; border:1px solid {BORDER};
                border-radius:6px; padding:6px 10px; font-size:12px; }}
            QComboBox::drop-down {{ border:none; }}
            QComboBox QAbstractItemView {{ background:{CARD}; color:{TEXT}; border:1px solid {BORDER}; }}
        """)
        self.exp_since.currentTextChanged.connect(lambda _: self._refresh_notes())
        frow.addWidget(self.exp_since)

        refresh = ghost_btn('↺', width=36)
        refresh.clicked.connect(self._refresh_notes)
        frow.addWidget(refresh)
        frow.addStretch()
        lay.addWidget(filt)

        # Note list
        self.note_list = QListWidget()
        self.note_list.setStyleSheet(f"""
            QListWidget {{ background:{DARK}; border:1px solid {BORDER}; border-radius:8px;
                color:{TEXT}; font-size:12px; }}
            QListWidget::item {{ padding:6px 10px; border-bottom:1px solid {BORDER}; }}
            QListWidget::item:hover {{ background:{CARD}; }}
        """)
        self.note_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        lay.addWidget(self.note_list, stretch=1)

        self.exp_count = label('Loading...', 11, color=MUTED)
        lay.addWidget(self.exp_count)

        # Buttons
        brow = QHBoxLayout()
        b1 = btn('Export Selected', width=180)
        b1.clicked.connect(self._export_raw)
        b2 = btn('Export + Summarize with Claude', color=GREEN)
        b2.clicked.connect(self._export_summarize)
        brow.addWidget(b1)
        brow.addWidget(b2)
        lay.addLayout(brow)

        b3 = ghost_btn('Open Export Folder in Finder')
        b3.clicked.connect(self._open_export_folder)
        b3.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay.addWidget(b3)

        return w

    # ── import tab ────────────────────────────────────────────────────────

    def _build_import_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lay.addWidget(label('Paste text from NotebookLM:', 13, bold=True))

        self.import_text = QTextEdit()
        self.import_text.setPlaceholderText('Paste your NotebookLM summary or notes here...')
        self.import_text.setStyleSheet(f"""
            QTextEdit {{ background:{DARK}; color:{TEXT}; border:1px solid {BORDER};
                border-radius:8px; padding:10px; font-size:13px; }}
        """)
        lay.addWidget(self.import_text, stretch=1)

        paste_btn = ghost_btn('Paste from Clipboard')
        paste_btn.clicked.connect(self._paste_clipboard)
        lay.addWidget(paste_btn)

        # Title + folder row
        meta_row = QHBoxLayout()
        meta_row.addWidget(label('Title:', 12, color=MUTED))
        self.import_title = entry('e.g. History Summary')
        meta_row.addWidget(self.import_title, stretch=2)
        meta_row.addWidget(label('Folder:', 12, color=MUTED))
        self.import_folder = entry('NotebookLM')
        meta_row.addWidget(self.import_folder, stretch=1)
        lay.addLayout(meta_row)

        brow = QHBoxLayout()
        b1 = btn('Save to Obsidian', width=180)
        b1.clicked.connect(lambda: self._do_import(False))
        b2 = btn('Save + Format with Claude', color=GREEN)
        b2.clicked.connect(lambda: self._do_import(True))
        brow.addWidget(b1)
        brow.addWidget(b2)
        lay.addLayout(brow)

        return w

    # ── md import tab ─────────────────────────────────────────────────────

    def _build_md_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lay.addWidget(label('Import Markdown files into your vault', 13, bold=True))

        pick_row = QHBoxLayout()
        b1 = btn('Pick Files…', width=130)
        b1.clicked.connect(self._pick_md_files)
        b2 = btn('Pick Folder…', width=130)
        b2.clicked.connect(self._pick_md_folder)
        self.md_count_label = label('No files selected', 12, color=MUTED)
        pick_row.addWidget(b1)
        pick_row.addWidget(b2)
        pick_row.addWidget(self.md_count_label)
        pick_row.addStretch()
        lay.addLayout(pick_row)

        self.md_list = QListWidget()
        self.md_list.setStyleSheet(f"""
            QListWidget {{ background:{DARK}; border:1px solid {BORDER}; border-radius:8px;
                color:{TEXT}; font-size:12px; }}
            QListWidget::item {{ padding:6px 10px; border-bottom:1px solid {BORDER}; }}
        """)
        lay.addWidget(self.md_list, stretch=1)

        dest_row = QHBoxLayout()
        dest_row.addWidget(label('Save to folder:', 12, color=MUTED))
        self.md_dest = entry('Claude Chats')
        self.md_dest.setText('Claude Chats')
        dest_row.addWidget(self.md_dest, stretch=1)
        self.md_clean = QCheckBox('Clean up with Claude')
        self.md_clean.setStyleSheet(f'color:{TEXT}; font-size:12px;')
        dest_row.addWidget(self.md_clean)
        lay.addLayout(dest_row)

        import_btn = btn('Import into Vault', color=GREEN)
        import_btn.clicked.connect(self._do_md_import)
        lay.addWidget(import_btn)

        return w

    # ── claude tab ────────────────────────────────────────────────────────

    def _build_claude_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lay.addWidget(label('Ask Claude about your notes:', 13, bold=True))

        self.claude_input = QTextEdit()
        self.claude_input.setPlaceholderText('e.g. Summarize my IB History notes as bullet points')
        self.claude_input.setFixedHeight(100)
        self.claude_input.setStyleSheet(f"""
            QTextEdit {{ background:{DARK}; color:{TEXT}; border:1px solid {BORDER};
                border-radius:8px; padding:10px; font-size:13px; }}
        """)
        lay.addWidget(self.claude_input)

        opt_row = QHBoxLayout()
        opt_row.addWidget(label('Context folder:', 12, color=MUTED))
        self.claude_folder = entry('All vault (leave blank)')
        opt_row.addWidget(self.claude_folder, stretch=1)
        ask_btn = btn('Ask Claude', width=120)
        ask_btn.clicked.connect(self._ask_claude)
        opt_row.addWidget(ask_btn)
        lay.addLayout(opt_row)

        lay.addWidget(label('Response:', 12, bold=True))

        self.claude_output = QTextEdit()
        self.claude_output.setReadOnly(True)
        self.claude_output.setStyleSheet(f"""
            QTextEdit {{ background:{DARK}; color:{TEXT}; border:1px solid {BORDER};
                border-radius:8px; padding:10px; font-size:13px; }}
        """)
        lay.addWidget(self.claude_output, stretch=1)

        brow = QHBoxLayout()
        copy_btn = ghost_btn('Copy Response')
        copy_btn.clicked.connect(self._copy_claude)
        save_btn = btn('Save to Obsidian')
        save_btn.clicked.connect(self._save_claude)
        brow.addWidget(copy_btn)
        brow.addWidget(save_btn)
        brow.addStretch()
        lay.addLayout(brow)

        return w

    # ── settings tab ──────────────────────────────────────────────────────

    def _build_settings_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(14)

        lay.addWidget(label('Settings', 16, bold=True))
        lay.addWidget(separator())

        def setting_row(lbl, widget):
            row = QHBoxLayout()
            l = label(lbl, 12, color=MUTED)
            l.setFixedWidth(140)
            row.addWidget(l)
            row.addWidget(widget, stretch=1)
            lay.addLayout(row)

        self.api_entry = entry('sk-ant-...', password=True)
        if self.cfg.get('anthropic_key'):
            self.api_entry.setText(self.cfg['anthropic_key'])
        setting_row('Anthropic API Key:', self.api_entry)

        self.vault_entry = entry(DEFAULT_VAULT)
        self.vault_entry.setText(self.vault_path)
        setting_row('Vault Path:', self.vault_entry)

        save = btn('Save Settings', width=140)
        save.clicked.connect(self._save_settings)
        lay.addWidget(save)

        lay.addWidget(label(
            'API key is stored in ~/.obsidian-bridge-config.json',
            11, color=MUTED
        ))
        lay.addStretch()
        return w

    # ── status bar ────────────────────────────────────────────────────────

    def _build_statusbar(self):
        f = QWidget()
        row = QHBoxLayout(f)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        self.progress = QProgressBar()
        self.progress.setFixedWidth(160)
        self.progress.setFixedHeight(6)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(f"""
            QProgressBar {{ background:{CARD}; border-radius:3px; border:none; }}
            QProgressBar::chunk {{ background:{PURPLE}; border-radius:3px; }}
        """)
        row.addWidget(self.progress)

        self.status_label = label('Ready', 12, color=MUTED)
        row.addWidget(self.status_label)
        row.addStretch()
        return f

    def _set_status(self, msg: str):
        self.status_label.setText(msg)

    def _set_busy(self, busy: bool):
        if busy:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)

    # ── open apps ─────────────────────────────────────────────────────────

    def _open_claude(self):
        try:
            open_app('Claude')
        except Exception:
            open_url('https://claude.ai')

    def _open_obsidian(self):
        try:
            open_app('Obsidian')
        except Exception:
            open_url('obsidian://')

    def _open_notebooklm(self):
        open_url('https://notebooklm.google.com')

    # ── note list ─────────────────────────────────────────────────────────

    def _refresh_notes(self):
        self._set_status('Loading notes...')
        since_map = {'Today': 0, '3 days': 3, '7 days': 7, '30 days': 30, 'All time': None}
        days = since_map.get(self.exp_since.currentText(), 7)
        since_date = date.today() - timedelta(days=days) if days is not None else None
        folder = self.exp_folder.text().strip() or None

        def load(emit, folder, since_date):
            from modules.vault import VaultReader
            reader = VaultReader(self.vault_path)
            return reader.read_notes(folder=folder, since=since_date)

        self._run(load, folder, since_date,
                  on_done=self._populate_notes, label='notes loaded')

    def _populate_notes(self, notes):
        self._notes = notes
        self.note_list.clear()
        for n in notes:
            item = QListWidgetItem(f"{n.title}   —   {n.folder}   ({n.modified.strftime('%b %d')})")
            item.setData(Qt.ItemDataRole.UserRole, n)
            self.note_list.addItem(item)
            item.setSelected(True)
        self.exp_count.setText(f'{len(notes)} notes')

    def _selected_notes(self):
        return [item.data(Qt.ItemDataRole.UserRole)
                for item in self.note_list.selectedItems()]

    # ── export ────────────────────────────────────────────────────────────

    def _export_raw(self):
        notes = self._selected_notes()
        if not notes:
            self._set_status('Select notes first')
            return
        def work(emit, notes):
            from modules.exporter import Exporter
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            exp = Exporter(str(EXPORT_DIR))
            exported = exp.export_individual(notes)
            exp.write_manifest(notes, exported)
            return len(exported)
        self._run(work, notes,
                  on_done=lambda n: (self._set_status(f'Exported {n} notes'), self._open_export_folder()),
                  label='exporting')

    def _export_summarize(self):
        notes = self._selected_notes()
        if not notes:
            self._set_status('Select notes first')
            return
        if not self._api_key():
            self._need_key(); return

        def work(emit, notes):
            from modules.exporter import Exporter
            from modules.processor import ClaudeProcessor
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            proc = ClaudeProcessor(self._api_key())
            processed = {}
            for i, note in enumerate(notes):
                emit(f'Summarizing {i+1}/{len(notes)}: {note.title}')
                processed[note.title] = proc.summarize_note(note)
            exp = Exporter(str(EXPORT_DIR))
            exported = exp.export_individual(notes, processed)
            exp.write_manifest(notes, exported)
            return len(exported)

        self._run(work, notes,
                  on_done=lambda n: (self._set_status(f'Exported & summarized {n} notes'), self._open_export_folder()),
                  label='summarizing')

    def _open_export_folder(self):
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(['open', str(EXPORT_DIR)])

    # ── import ────────────────────────────────────────────────────────────

    def _paste_clipboard(self):
        cb = QApplication.clipboard()
        self.import_text.setPlainText(cb.text())

    def _do_import(self, format_with_claude: bool):
        text = self.import_text.toPlainText().strip()
        if not text:
            self._set_status('No text to save')
            return
        title = self.import_title.text().strip() or 'NotebookLM Note'
        folder = self.import_folder.text().strip() or 'NotebookLM'
        if format_with_claude and not self._api_key():
            self._need_key(); return

        def work(emit, text, title, folder, fmt):
            if fmt:
                from modules.processor import ClaudeProcessor
                proc = ClaudeProcessor(self._api_key())
                path = proc.save_to_obsidian(text, title, self.vault_path, folder)
            else:
                out_dir = Path(self.vault_path) / folder
                out_dir.mkdir(parents=True, exist_ok=True)
                safe = ''.join(c for c in title if c.isalnum() or c in ' -_').strip()
                path = str(out_dir / f'{safe}.md')
                Path(path).write_text(f'# {title}\n\n{text}', encoding='utf-8')
            rel = Path(path).relative_to(self.vault_path)
            open_url(f"obsidian://open?path={urllib.parse.quote(str(rel))}")
            return title

        self._run(work, text, title, folder, format_with_claude,
                  on_done=lambda t: self._set_status(f'Saved "{t}" to Obsidian'),
                  label='saving')

    # ── md import ─────────────────────────────────────────────────────────

    def _pick_md_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Select Markdown Files', str(Path.home() / 'Desktop'),
            'Markdown (*.md);;All Files (*)'
        )
        if paths:
            self._md_files = [Path(p) for p in paths]
            self._populate_md_list()

    def _pick_md_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, 'Select Folder', str(Path.home() / 'Desktop')
        )
        if folder:
            self._md_files = list(Path(folder).rglob('*.md'))
            self._populate_md_list()

    def _populate_md_list(self):
        self.md_list.clear()
        for f in self._md_files:
            size_kb = round(f.stat().st_size / 1024, 1)
            self.md_list.addItem(f'{f.name}  ({size_kb} KB)')
        n = len(self._md_files)
        self.md_count_label.setText(f'{n} file{"s" if n != 1 else ""} selected')

    def _do_md_import(self):
        if not self._md_files:
            self._set_status('No files selected')
            return
        dest = self.md_dest.text().strip() or 'Claude Chats'
        clean = self.md_clean.isChecked()
        if clean and not self._api_key():
            self._need_key(); return

        files = list(self._md_files)

        def work(emit, files, dest, clean):
            import anthropic as ac
            out_dir = Path(self.vault_path) / dest
            out_dir.mkdir(parents=True, exist_ok=True)
            client = ac.Anthropic(api_key=self._api_key()) if clean else None
            count = 0
            for i, src in enumerate(files):
                emit(f'Importing {i+1}/{len(files)}: {src.name}')
                content = src.read_text(encoding='utf-8', errors='replace')
                if clean and client:
                    resp = client.messages.create(
                        model='claude-sonnet-4-6',
                        max_tokens=4096,
                        messages=[{
                            'role': 'user',
                            'content': (
                                'Clean up this Claude-generated markdown file for Obsidian. '
                                'Add YAML frontmatter (tags, date). Keep all content.\n\n'
                                + content
                            ),
                        }],
                    )
                    content = resp.content[0].text
                dest_file = out_dir / src.name
                counter = 1
                while dest_file.exists():
                    dest_file = out_dir / f'{src.stem} ({counter}){src.suffix}'
                    counter += 1
                dest_file.write_text(content, encoding='utf-8')
                count += 1
            return (count, dest)

        self._run(work, files, dest, clean,
                  on_done=lambda r: (
                      self._set_status(f'Imported {r[0]} file(s) → {r[1]}/'),
                      subprocess.Popen(['open', str(Path(self.vault_path) / r[1])])
                  ),
                  label='importing')

    # ── ask claude ────────────────────────────────────────────────────────

    def _ask_claude(self):
        if not self._api_key():
            self._need_key(); return
        prompt = self.claude_input.toPlainText().strip()
        if not prompt:
            return
        folder = self.claude_folder.text().strip() or None

        def work(emit, prompt, folder):
            from modules.vault import VaultReader, clean_obsidian_syntax
            import anthropic as ac
            emit('Reading vault...')
            reader = VaultReader(self.vault_path)
            notes = reader.read_notes(folder=folder)[:20]
            context = '\n\n---\n\n'.join(
                f'## {n.title}\n\n{clean_obsidian_syntax(n.content)}' for n in notes
            )
            emit('Asking Claude...')
            client = ac.Anthropic(api_key=self._api_key())
            resp = client.messages.create(
                model='claude-sonnet-4-6',
                max_tokens=2048,
                messages=[{
                    'role': 'user',
                    'content': f'Obsidian notes:\n\n{context}\n\n---\n\n{prompt}',
                }],
            )
            return resp.content[0].text

        self._run(work, prompt, folder,
                  on_done=self._show_claude_response,
                  label='thinking')

    def _show_claude_response(self, text):
        self._last_claude = text
        self.claude_output.setPlainText(text)
        self._set_status('Claude responded')

    def _copy_claude(self):
        if self._last_claude:
            QApplication.clipboard().setText(self._last_claude)
            self._set_status('Copied to clipboard')

    def _save_claude(self):
        if not self._last_claude:
            return
        out_dir = Path(self.vault_path) / 'Claude'
        out_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        fname = f"Claude {datetime.now().strftime('%Y-%m-%d %H%M')}.md"
        prompt = self.claude_input.toPlainText().strip()
        (out_dir / fname).write_text(
            f'---\ntags: [claude]\ndate: {date.today()}\n---\n\n'
            f'# Claude Response\n\n**Prompt:** {prompt}\n\n---\n\n{self._last_claude}',
            encoding='utf-8'
        )
        open_url(f"obsidian://open?path={urllib.parse.quote('Claude/' + fname)}")
        self._set_status(f'Saved → Claude/{fname}')

    # ── settings ──────────────────────────────────────────────────────────

    def _save_settings(self):
        key = self.api_entry.text().strip()
        vault = self.vault_entry.text().strip()
        if key:
            self.cfg['anthropic_key'] = key
        if vault:
            self.cfg['vault_path'] = vault
            self.vault_path = vault
        save_config(self.cfg)
        self._set_status('Settings saved')

    def _api_key(self) -> str:
        return self.cfg.get('anthropic_key') or os.environ.get('ANTHROPIC_API_KEY', '')

    def _need_key(self):
        self._set_status('Add your Anthropic API key in the Settings tab')

    # ── worker helper ─────────────────────────────────────────────────────

    def _run(self, fn, *args, on_done=None, label='working'):
        self._set_busy(True)
        self._set_status(label.capitalize() + '...')
        self._worker = Worker(fn, *args)
        self._worker.status.connect(self._set_status)
        if on_done:
            self._worker.done.connect(lambda r: (self._set_busy(False), on_done(r)))
        else:
            self._worker.done.connect(lambda _: self._set_busy(False))
        self._worker.error.connect(lambda e: (self._set_busy(False), self._set_status(f'Error: {e}')))
        self._worker.start()


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName('Bridge')
    app.setStyle('Fusion')

    # macOS: make it a proper foreground app with dock icon
    try:
        from AppKit import NSApplication, NSApp
        NSApplication.sharedApplication()
        NSApp.setActivationPolicy_(0)
        NSApp.activateIgnoringOtherApps_(True)
    except Exception:
        pass

    window = BridgeApp()
    window.show()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())
