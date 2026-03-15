# Getting Started

## Requirements

- Python 3.10 or newer
- tkinter (included with most Python installations, required for GUI mode only)

## Installation

### From source (recommended)

```bash
git clone https://forgejo.darkhorseinfosec.com/username/DirCompare.git
cd DirCompare
pip install .
```

### Run without installing

```bash
python -m DirCompare
```

## First Comparison

### GUI Mode

```bash
dircompare
# or
python -m DirCompare
```

1. Enter or browse to the left and right directory paths
2. Click **Compare** (or press F5)
3. Review the results in the treeview
4. Double-click any file to see a diff

### CLI Mode

```bash
dircompare --left /path/to/original --right /path/to/backup
```

The exit code tells you the result:

| Code | Meaning |
|------|---------|
| 0 | Directories are equivalent |
| 10 | Left directory is more up to date |
| 20 | Right directory is more up to date |
| 1 | Error |
