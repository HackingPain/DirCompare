# GUI Guide

## Launching

```bash
dircompare
# or with pre-filled directories:
dircompare /path/to/left /path/to/right
```

## Main Window

The main window contains:

- **Directory pickers** — Enter paths or click Browse. Use the ⇄ button to swap.
- **Ignore patterns** — Shows a count of active patterns. Click Edit to customise.
- **Compare button** — Starts the comparison (F5 or Ctrl+Enter).
- **Progress bar** — Shows scan and analysis progress with file counts.
- **Summary panel** — Displays the verdict, score, confidence, and file statistics.
- **Results treeview** — Lists all compared files with status, sizes, and notes.
- **Filter checkboxes** — Toggle visibility of each status category.
- **Search box** — Filter results by filename (Ctrl+F to focus).

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| F5 / Ctrl+Enter | Start comparison |
| Shift+F5 | Re-compare |
| Escape | Cancel comparison |
| Ctrl+E | Export report |
| Ctrl+S | Swap directories |
| Ctrl+F | Focus search box |
| F1 | About DirCompare |

## Diff Viewer

Double-click any file row to open the diff viewer, which supports:

- **Unified diff** — Standard unified format with context lines
- **Side-by-side diff** — Two-panel comparison with synchronised scrolling

## Menus

- **History > View History** — Browse past comparisons, double-click to re-run
- **History > Clear History** — Remove all saved history
- **Help > Keyboard Shortcuts** — Quick reference
- **Help > About DirCompare** — Version and license information

## Settings

Click the Settings button to configure:

- **Scoring Weights** — Adjust the weight for each scoring signal
- **Hash Algorithm** — Choose between MD5 (faster) and SHA-256 (more secure)
