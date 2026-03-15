# DirCompare

**Compare two directories and determine which is more up to date.**

DirCompare is the only tool that answers the question: _"Which copy of my project is newer?"_

It uses content fingerprinting (MD5 or SHA-256), version-string detection, git commit counts, and a configurable weighted scoring system to produce an automated freshness verdict. Zero external dependencies — only the Python standard library.

## Key Features

- **Automated freshness verdict** — scored analysis, not just a diff listing
- **Multi-signal scoring** — unique files, content fingerprints, version strings, git history
- **Configurable weights** — tune the scoring formula for your workflow
- **Dual interface** — full tkinter GUI and comprehensive CLI
- **Four export formats** — text, CSV, JSON, HTML
- **Watch mode** — monitor directories and re-compare on changes
- **Plugin system** — extend scoring with custom signals
- **Comparison history** — track past results
- **Zero dependencies** — pure Python standard library

## Quick Start

```bash
pip install .
dircompare                               # launches GUI
dircompare --left dir1/ --right dir2/    # CLI mode
```

See [Getting Started](getting-started.md) for detailed installation instructions.
