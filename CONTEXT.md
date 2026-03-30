# Bridge — Build Context & Next Steps

## What's been built

A macOS dock app (`app.py`) + CLI (`bridge.py`) that links Obsidian, Claude AI, and NotebookLM.

### App structure
- **`app.py`** — PyQt6 dock app (dark theme, 5 tabs)
- **`bridge.py`** — CLI tool (same features, terminal-based)
- **`menubar.py`** — Menu bar app (⟁ in status bar, quick actions)
- **`modules/vault.py`** — Reads Obsidian vault, filters by folder/tag/date, strips Obsidian syntax
- **`modules/processor.py`** — Claude API: summarize notes, synthesize, save NotebookLM output back to vault
- **`modules/exporter.py`** — Bundles notes as clean markdown files for NotebookLM upload
- **`modules/gdrive.py`** — Uploads export bundles to Google Drive (NotebookLM can read directly)

### App tabs
| Tab | What it does |
|---|---|
| Obsidian → NotebookLM | Select notes, export raw or Claude-summarized, opens Finder |
| NotebookLM → Obsidian | Paste text, save as note (raw or Claude-formatted), opens in Obsidian |
| Import MDs | Pick .md files or folder → imports into vault (e.g. Claude-generated chat exports) |
| Ask Claude | Type a question, Claude reads your vault as context, save response to Obsidian |
| Settings | Anthropic API key, vault path |

### .app bundle
- Located at `~/Applications/Bridge.app`
- Shell launcher → framework Python → `app.py`
- Has custom icon (3-node graph: purple=Claude, indigo=Obsidian, green=NotebookLM)

---

## Current blocker

**The dock app window is not appearing** when launched via `open Bridge.app`.

- The Python process starts and runs fine (confirmed via `ps`)
- Switching from tkinter → PyQt6 fixed the `NSInvalidArgumentException` crash
- But the window still doesn't come to front when launched as a `.app`
- Launching directly (`python3 app.py`) works fine — window appears

### Suspected causes
1. The shell-script-based `.app` launcher doesn't hand off window focus correctly to macOS
2. macOS Gatekeeper or Accessibility permissions blocking window activation
3. PyQt6 app needs to be launched via `pythonw` or directly as a Python.app process (not via bash wrapper)

### What to try next
- Change the `.app` bundle `CFBundleExecutable` to call Python directly (not via shell script)
- Use `py2app` or `PyInstaller` to build a proper self-contained `.app`
- Try `pythonw` instead of `python3` in the launcher script
- Check System Preferences → Privacy & Security → Accessibility for Bridge

---

## Remaining features to build

### High priority
- [ ] **Fix dock app window appearing** (current blocker — see above)
- [ ] **Watch folder for new MDs** — auto-import when Claude drops a new .md file into a watched folder (e.g. Downloads)
- [ ] **Drag & drop** — drag .md files directly onto the app window to import

### Medium priority
- [ ] **NotebookLM → Obsidian via Google Drive** — poll a Drive folder for new files, auto-import
- [ ] **Tag picker UI** — instead of typing tags, show vault tags as clickable chips in the export filter
- [ ] **Preview pane** — click a note in the list to preview its content before exporting
- [ ] **Conflict resolution UI** — when importing a file that already exists, ask user: overwrite / rename / skip

### Low priority / nice to have
- [ ] **Export to PDF** — bundle notes as a PDF for NotebookLM upload (using `weasyprint` or `pandoc`)
- [ ] **Google Drive auto-sync** — keep an "always-on" Drive folder synced with selected vault folders
- [ ] **Menu bar quick-capture** — type a quick note from the menu bar, saves directly to vault
- [ ] **NotebookLM source links** — after uploading to Drive, store the Drive links inside the Obsidian note as metadata

---

## Setup instructions (for resuming)

```bash
cd ~/obsidian-bridge

# Install deps
pip3 install -r requirements.txt

# Run app directly (works)
python3 app.py

# Or launch as dock app (window focus bug pending fix)
open ~/Applications/Bridge.app

# CLI usage
python3 bridge.py list
python3 bridge.py export --folder "IB Notes" --merged --output ~/Desktop/bundle
```

Config is stored at `~/.obsidian-bridge-config.json`
Vault: `/Users/adityatotlani/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Notes`
