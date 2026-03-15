"""
DirCompare – Compare two directories and determine which is more up to date.

Uses content fingerprinting (MD5 or SHA-256), version-string detection, git commit
counts, and a weighted scoring system.  Ships with both a tkinter GUI
(default) and a CLI interface.

Usage
-----
GUI (default)::

    python -m DirCompare

CLI::

    python -m DirCompare --left /path/a --right /path/b

See ``python -m DirCompare --help`` for all options.
"""

from .engine import (  # noqa: F401 – re-exported for public API
    ComparisonResult,
    ComparisonRow,
    DEFAULT_IGNORE_PATTERNS,
    FileInfo,
    FileStatus,
    IGNORE_CATEGORIES,
    ScoringWeights,
    compare_directories,
    compute_merkle_hash,
    export_report_csv,
    export_report_html,
    export_report_json,
    export_report_txt,
    fmt_size,
)

__version__ = "1.3.0"
SUPPORTED_HASH_ALGORITHMS = ("md5", "sha256")
__all__ = [
    "ComparisonResult",
    "ComparisonRow",
    "DEFAULT_IGNORE_PATTERNS",
    "FileInfo",
    "FileStatus",
    "IGNORE_CATEGORIES",
    "ScoringWeights",
    "compare_directories",
    "compute_merkle_hash",
    "export_report_csv",
    "export_report_html",
    "export_report_json",
    "export_report_txt",
    "fmt_size",
    "SUPPORTED_HASH_ALGORITHMS",
]
