# Changelog

All notable changes to DirCompare will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No unreleased changes._

## [1.3.0] - 2026-02-28

### Added
- SHA-256 hash algorithm option (`--hash-algorithm` / `-H` flag, GUI settings)
- Application icon and window branding
- Menu bar with Help menu (About dialog, Keyboard Shortcuts reference)
- Watch mode for continuous directory monitoring (`--watch` flag)
- Comparison history with persistent storage (`--history` flag)
- Plugin system for custom scoring signals (`~/.dircompare/plugins/`)
- Performance benchmark suite
- Documentation site structure (MkDocs Material theme)
- CI pipeline configuration (Forgejo Actions)
- Standalone executable support via PyInstaller (GUI + CLI .exe)
- CHANGELOG.md
- Comprehensive documentation (8 pages: Getting Started, CLI Reference, GUI Guide, Scoring Algorithm, Plugin API, Benchmarks, Changelog)

## [1.2.0] - 2026-02-28

### Added
- `pyproject.toml` for pip-installable packaging
- Proper Python package structure with relative imports
- Logging module replacing print-to-stderr
- README.md with full usage documentation
- LICENSE file (MIT)
- `.gitignore` for Python projects

### Changed
- Converted all bare imports to relative imports
- Bumped minimum setuptools to 64

### Fixed
- Flaky GUI test from Tk handle exhaustion (graceful skip)
- Package structure for `pip install .` compatibility
- `testpaths` in pyproject.toml pointing to correct directory

## [1.1.0] - 2026-02-28

### Added
- Side-by-side diff viewer alongside unified diff view
- Ignore patterns dialog with 18 category-based quick-add checkboxes
- Column sorting in results treeview (click any heading)
- Right-click context menu for copying paths and opening in file explorer
- Lazy loading pagination for large result sets (5,000+ files)
- Debounced search filtering with real-time results
- Placeholder text in directory entry fields
- Tooltips showing full file paths on hover
- Copy Summary button
- Re-compare button with Shift+F5 shortcut
- Filtered-only export option
- Score breakdown in all report formats
- File type counts in summary and reports
- Timestamp on all reports
- Window title shows verdict after comparison
- `.gitignore` parsing support (`--gitignore` flag)
- Configurable scoring weights (`--weights` flag, Settings dialog)
- Progress bar with stage indicators and file count messages
- Cancel button for long-running comparisons
- Four export formats: text, CSV, JSON, HTML
- HTML reports with colour-coded status rows
- Comprehensive test suite (331 tests)

### Changed
- Ignore patterns displayed as count summary with Edit button
- Column headings update to show directory names after comparison

## [1.0.0] - 2026-02-28

### Added
- Initial release
- Directory comparison via MD5 content fingerprinting
- Version-string detection with regex patterns
- Git commit count integration
- Weighted scoring system (unique files, content analysis, version strings, git commits)
- Confidence levels: High (|score| >= 8), Medium (|score| >= 3), Low
- tkinter GUI with treeview display and colour-coded rows
- CLI interface with `--left` / `--right` arguments
- Default ignore patterns for 18 language/tool categories
- Exit codes: 0 (equivalent), 10 (left newer), 20 (right newer), 1 (error)
- Parallel directory scanning with ThreadPoolExecutor
- Single-pass file reading (hash + binary detection + text analysis)
- Binary file detection via null-byte scanning
- Text analysis: line count, word count, character count
- 50 MB size limit for text analysis
