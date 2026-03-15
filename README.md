# DirCompare

Compare two directories and determine which is more up to date.

DirCompare uses content fingerprinting (MD5), version-string detection, git
commit counts, and a weighted scoring system to decide which directory
contains the newer codebase. It ships with both a **tkinter GUI** (default)
and a **CLI** interface. Zero external dependencies -- only the Python
standard library is required.

## Installation

```bash
pip install .
```

Or run directly without installing:

```bash
python -m DirCompare
```

Requires **Python 3.10+**.

## Usage

### GUI (default)

```bash
python -m DirCompare
# or after pip install:
dircompare
```

Launch with directories pre-filled:

```bash
python -m DirCompare /path/to/left /path/to/right
```

### CLI

```bash
python -m DirCompare --left /path/a --right /path/b
```

#### Options

| Flag | Short | Description |
|------|-------|-------------|
| `--left PATH` | `-l` | Left directory path |
| `--right PATH` | `-r` | Right directory path |
| `--format FMT` | `-f` | Output format: `text`, `csv`, `json`, `html` |
| `--output FILE` | `-o` | Write report to file instead of stdout |
| `--ignore PATS` | `-i` | Comma-separated ignore patterns |
| `--gitignore` | | Parse `.gitignore` files for extra patterns |
| `--weights W` | | Custom scoring weights `unique:content:version:git` |
| `--quiet` | `-q` | Suppress progress output |

#### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Directories are equivalent |
| `1` | Error (invalid path, permission denied, etc.) |
| `10` | Left directory is more up to date |
| `20` | Right directory is more up to date |

#### Examples

```bash
# JSON report to file
python -m DirCompare -l src/ -r backup/src/ -f json -o report.json

# Custom scoring weights (unique=5, content=1, version=3, git=2)
python -m DirCompare -l v1/ -r v2/ --weights 5:1:3:2

# Respect .gitignore, quiet mode
python -m DirCompare -l repo1/ -r repo2/ --gitignore -q
```

## How it works

1. **Scan** -- walks both directory trees in parallel, hashing each file
   (MD5) and collecting metadata (line counts, word counts, version strings).
2. **Compare** -- matches files by relative path. Identical hashes are marked
   equal; differing files are scored by content volume and per-file version
   strings.
3. **Score** -- a weighted sum of unique-file counts, content analysis,
   global version strings, and git commit counts produces a single integer
   score. Negative means left is newer, positive means right is newer.
4. **Report** -- results are presented in the GUI treeview or exported as
   plain text, CSV, JSON, or a self-contained HTML report.

## Scoring weights

The default weights are:

| Signal | Default weight |
|--------|---------------|
| Unique file | 3 |
| Content analysis | 1 |
| Version string | 2 |
| Git commits | 2 |

Override with `--weights unique:content:version:git`, e.g. `--weights 5:1:3:2`.

## Ignore patterns

DirCompare ships with a comprehensive set of default ignore patterns covering
Python, JavaScript/Node, Java, C/C++, .NET, Go, Rust, Ruby, PHP, Swift, Dart,
R, version control, IDE files, OS artifacts, environment files, caches,
coverage outputs, and infrastructure tools.

Patterns can be customised with `--ignore` or managed interactively through
the GUI's ignore-patterns dialog, which groups them by category.

## Project structure

```
DirCompare/                # Project root
    DirCompare/            # Python package
        __init__.py        # Package API and re-exports
        __main__.py        # CLI entry point
        engine.py          # Core comparison logic, scanning, scoring, export
        gui.py             # Tkinter GUI
    test_engine.py         # Engine unit tests
    test_main.py           # CLI unit tests
    test_gui.py            # GUI unit tests
    pyproject.toml         # Packaging configuration
    LICENSE                # MIT license
    README.md              # This file
```

## Documentation

Detailed documentation is available in the `docs/` directory:

- [Getting Started](docs/getting-started.md)
- [CLI Reference](docs/cli-reference.md)
- [GUI Guide](docs/gui-guide.md)
- [Scoring Algorithm](docs/scoring.md)
- [Plugin API](docs/plugin-api.md)
- [Benchmarks](docs/benchmarks.md)
- [Changelog](CHANGELOG.md)

To build the documentation site locally:

```bash
pip install mkdocs-material
mkdocs serve
```

## Running tests

```bash
python -m pytest -q
```

## License

MIT
