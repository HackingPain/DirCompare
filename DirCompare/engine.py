"""
DirCompare Engine
Core comparison logic: scanning, hashing, content analysis, scoring, and export.
Uses only Python standard library.
"""

import csv
import hashlib
import io
import json
import logging
import os
import re
import subprocess
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_FILENAME = ".dircompare_cache.json"


# ---------------------------------------------------------------------------
# Default Ignore Patterns — single source of truth
# ---------------------------------------------------------------------------

IGNORE_CATEGORIES: dict[str, str] = {
    "Python": "__pycache__, *.pyc, *.pyo, *.pyd, *.egg-info, dist, build, .eggs, *.whl, .mypy_cache, .ruff_cache, .pytest_cache, .tox, .nox, .venv, venv",
    "JavaScript/Node": "node_modules, .npm, .yarn, .pnp.*, bower_components, .eslintcache",
    "Java/JVM": "target, *.class, *.jar, *.war, *.ear, .gradle, .m2",
    "C/C++": "*.o, *.obj, *.a, *.lib, *.so, *.dylib, *.dll, *.exe, CMakeFiles, CMakeCache.txt",
    "C#/.NET": "bin, obj, *.nupkg, packages",
    "Go": "vendor",
    "Rust": "target, *.rlib",
    "Ruby": ".bundle",
    "PHP": "vendor",
    "Swift/Xcode": ".build, DerivedData, *.xcworkspace, Pods",
    "Dart/Flutter": ".dart_tool, .flutter-plugins",
    "R": ".Rhistory, .RData",
    "Version Control": ".git, .svn, .hg, .bzr",
    "IDE/Editor": ".vscode, .idea, *.swp, *.swo, *~, .project, .settings, .eclipse, *.sublime-workspace",
    "OS Artifacts": ".DS_Store, Thumbs.db, desktop.ini, ehthumbs.db",
    "Environment": ".env, .env.*, *.pem, *.key",
    "Caches": ".cache, .parcel-cache, .next, .nuxt, .turbo, .sass-cache, .dircompare_cache.json",
    "Coverage/Logs": "htmlcov, .coverage, *.log, coverage, .nyc_output",
    "Infrastructure": ".terraform, .vagrant, .serverless",
}


def _flatten_categories(categories: dict[str, str]) -> list[str]:
    """Flatten category dict into a deduplicated list of patterns."""
    seen: set[str] = set()
    result: list[str] = []
    for patterns_str in categories.values():
        for p in patterns_str.split(","):
            p = p.strip()
            if p and p not in seen:
                seen.add(p)
                result.append(p)
    return result


DEFAULT_IGNORE_PATTERNS: list[str] = _flatten_categories(IGNORE_CATEGORIES)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class FileStatus(Enum):
    LEFT_ONLY = "Left Only"
    RIGHT_ONLY = "Right Only"
    IDENTICAL = "Identical"
    LEFT_NEWER = "Left Newer"
    RIGHT_NEWER = "Right Newer"
    UNKNOWN = "Unknown"


@dataclass
class ScoringWeights:
    """Configurable weights for the freshness scoring system."""
    unique_file: int = 3
    content_analysis: int = 1
    version_string: int = 2
    git_commits: int = 2


@dataclass
class FileInfo:
    rel_path: str
    abs_path: str
    size: int
    content_hash: str
    is_binary: bool
    line_count: int = 0
    word_count: int = 0
    char_count: int = 0
    version_strings: list[str] = field(default_factory=list)
    error: Optional[str] = None
    hash_algorithm: str = "md5"


@dataclass
class ComparisonRow:
    rel_path: str
    status: FileStatus
    size_left: Optional[int]
    size_right: Optional[int]
    notes: str
    left_path: Optional[str] = None
    right_path: Optional[str] = None


@dataclass
class ComparisonResult:
    left_dir: str
    right_dir: str
    left_file_count: int
    right_file_count: int
    left_total_size: int
    right_total_size: int
    left_versions: list[str]
    right_versions: list[str]
    score: int          # positive = right newer, negative = left newer
    confidence: str
    explanation: str
    rows: list[ComparisonRow]
    warnings: list[str] = field(default_factory=list)
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    left_git_commits: Optional[int] = None
    right_git_commits: Optional[int] = None
    status_counts: dict[str, int] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: "")
    file_type_counts: dict[str, int] = field(default_factory=dict)
    score_breakdown: dict[str, int] = field(default_factory=dict)
    left_merkle_hash: str = ""
    right_merkle_hash: str = ""


# ---------------------------------------------------------------------------
# Ignore Pattern Matching
# ---------------------------------------------------------------------------

def parse_gitignore(dir_path: str) -> list[str]:
    """Parse .gitignore from a directory, returning a list of ignore patterns."""
    patterns = []
    gitignore_path = os.path.join(dir_path, '.gitignore')
    if not os.path.isfile(gitignore_path):
        return patterns
    try:
        with open(gitignore_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('!'):
                    continue  # negation not supported, skip
                line = line.rstrip('/')
                patterns.append(line)
    except OSError:
        pass
    return patterns


def should_ignore(rel_path: str, ignore_patterns: list[str]) -> bool:
    """Check if a relative path matches any ignore pattern."""
    parts = Path(rel_path).parts
    for pattern in ignore_patterns:
        pattern = pattern.strip()
        if not pattern:
            continue
        for part in parts:
            if _match_pattern(part, pattern):
                return True
        if _match_pattern(rel_path, pattern):
            return True
    return False


_pattern_cache: dict[str, re.Pattern] = {}


def _match_pattern(text: str, pattern: str) -> bool:
    """Simple glob-like matching: * matches anything, ? matches one char."""
    if '*' not in pattern and '?' not in pattern:
        return text == pattern

    compiled = _pattern_cache.get(pattern)
    if compiled is None:
        regex = ''
        i = 0
        while i < len(pattern):
            ch = pattern[i]
            if ch == '*':
                # Handle ** (matches path separators too)
                if i + 1 < len(pattern) and pattern[i + 1] == '*':
                    regex += '.*'
                    i += 2
                    continue
                regex += '[^/\\\\]*'
            elif ch == '?':
                regex += '[^/\\\\]'
            else:
                regex += re.escape(ch)
            i += 1
        compiled = re.compile(regex, re.IGNORECASE)
        _pattern_cache[pattern] = compiled

    return compiled.fullmatch(text) is not None


# ---------------------------------------------------------------------------
# Version Patterns (with word boundaries to reduce false positives)
# ---------------------------------------------------------------------------

VERSION_PATTERNS = [
    re.compile(r'\bv(\d+\.\d+(?:\.\d+){0,2})\b', re.IGNORECASE),
    re.compile(r'\bversion\s*[=:]\s*["\']?(\d+\.\d+(?:\.\d+){0,2})', re.IGNORECASE),
    re.compile(r'\brevision\s*[=:]\s*["\']?(\d+(?:\.\d+)*)', re.IGNORECASE),
    re.compile(r'__version__\s*=\s*["\'](\d+\.\d+(?:\.\d+)?)["\']'),
    re.compile(r'\b(20[12]\d-\d{2}-\d{2})\b'),
]


# ---------------------------------------------------------------------------
# Single-Pass File Scanning
# ---------------------------------------------------------------------------

MAX_TEXT_ANALYSIS_SIZE = 50 * 1024 * 1024  # Skip text analysis above 50 MB


def scan_file(abs_path: str, rel_path: str, hash_algorithm: str = "md5") -> FileInfo:
    """Scan a single file in one pass: hash + binary detection + text analysis.

    Reads the file exactly once, simultaneously computing a content hash
    (using the configurable hash algorithm, e.g. md5 or sha256),
    detecting binary content, and (for text files) analyzing lines/words/versions.
    """
    error = None
    size = 0
    content_hash = ''
    is_bin = False
    line_count = word_count = char_count = 0
    version_strings: list[str] = []

    try:
        # Resolve symlinks
        original_path = abs_path
        if os.path.islink(abs_path):
            abs_path = os.path.realpath(abs_path)
            if not os.path.exists(abs_path):
                return FileInfo(
                    rel_path=rel_path, abs_path=original_path, size=0,
                    content_hash='', is_binary=True, error="broken symlink",
                    hash_algorithm=hash_algorithm,
                )

        size = os.path.getsize(abs_path)
        hasher = hashlib.new(hash_algorithm)
        binary_checked = False
        text_chunks: list[bytes] = []

        with open(abs_path, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                hasher.update(chunk)

                if not binary_checked:
                    is_bin = b'\x00' in chunk
                    binary_checked = True

                # Accumulate text chunks only for text files under the size limit
                if not is_bin and size <= MAX_TEXT_ANALYSIS_SIZE:
                    text_chunks.append(chunk)

        content_hash = hasher.hexdigest()

        # Analyze text content from the chunks we already read
        if not is_bin and text_chunks:
            text = b''.join(text_chunks).decode('utf-8', errors='replace')
            text_chunks = []  # free memory
            for line in text.splitlines():
                line_count += 1
                word_count += len(line.split())
                chars_in_line = len(line)
                char_count += chars_in_line
                for pat in VERSION_PATTERNS:
                    for m in pat.finditer(line):
                        v = m.group(1)
                        if v and v not in version_strings:
                            version_strings.append(v)

    except PermissionError:
        error = "permission denied"
    except OSError as e:
        error = str(e)

    return FileInfo(
        rel_path=rel_path, abs_path=abs_path, size=size, content_hash=content_hash,
        is_binary=is_bin, line_count=line_count, word_count=word_count,
        char_count=char_count, version_strings=version_strings, error=error,
        hash_algorithm=hash_algorithm,
    )


# ---------------------------------------------------------------------------
# Progress Throttling
# ---------------------------------------------------------------------------

class ProgressThrottle:
    """Wraps a progress callback to fire at most every `interval` seconds."""

    def __init__(self, callback, interval: float = 0.05):
        self._callback = callback
        self._interval = interval
        self._last_time = 0.0

    def update(self, fraction: float, message: str = ""):
        now = time.monotonic()
        if fraction >= 1.0 or now - self._last_time >= self._interval:
            self._last_time = now
            self._callback(fraction, message)


# ---------------------------------------------------------------------------
# Directory Scanning
# ---------------------------------------------------------------------------

def scan_directory(
    dir_path: str,
    ignore_patterns: list[str],
    progress_callback=None,
    cancel_event: Optional[threading.Event] = None,
    use_gitignore: bool = False,
    hash_algorithm: str = "md5",
    use_cache: bool = False,
) -> dict[str, FileInfo]:
    """Recursively scan a directory and build a file inventory."""
    inventory: dict[str, FileInfo] = {}
    dir_path = os.path.realpath(dir_path)

    # First pass: collect file list (fast, no I/O per file)
    all_files: list[tuple[str, str]] = []

    # Accumulate gitignore patterns per-directory
    gitignore_patterns: list[str] = []

    for root, dirs, files in os.walk(dir_path, followlinks=False):
        # Pick up .gitignore from this directory if recursive gitignore is enabled
        if use_gitignore:
            local_gi = parse_gitignore(root)
            if local_gi:
                gitignore_patterns.extend(local_gi)

        combined_patterns = ignore_patterns + gitignore_patterns

        dirs[:] = [
            d for d in dirs
            if not should_ignore(
                os.path.relpath(os.path.join(root, d), dir_path), combined_patterns
            )
        ]
        for fname in files:
            rel = os.path.relpath(os.path.join(root, fname), dir_path)
            rel = rel.replace('\\', '/')
            if rel == CACHE_FILENAME:
                continue
            if not should_ignore(rel, combined_patterns):
                all_files.append((os.path.join(root, fname), rel))

    # Load hash cache if enabled
    cache = None
    if use_cache:
        from .cache import HashCache
        cache = HashCache(dir_path, hash_algorithm)
        cache.load()

    total = len(all_files)
    throttle = ProgressThrottle(progress_callback) if progress_callback else None

    for idx, (abs_path, rel_path) in enumerate(all_files):
        if cancel_event and cancel_event.is_set():
            break

        # Try cache first
        if cache is not None:
            try:
                st = os.stat(abs_path)
                cached = cache.lookup(rel_path, st.st_size, st.st_mtime)
                if cached is not None:
                    inventory[rel_path] = FileInfo(
                        rel_path=rel_path,
                        abs_path=abs_path,
                        size=cached["size"],
                        content_hash=cached["content_hash"],
                        is_binary=cached["is_binary"],
                        line_count=cached.get("line_count", 0),
                        word_count=cached.get("word_count", 0),
                        char_count=cached.get("char_count", 0),
                        version_strings=cached.get("version_strings", []),
                        hash_algorithm=hash_algorithm,
                    )
                    if throttle and total > 0:
                        throttle.update(
                            (idx + 1) / total,
                            f"Hashing: {idx + 1:,}/{total:,} files (cached)",
                        )
                    continue
            except OSError:
                pass

        info = scan_file(abs_path, rel_path, hash_algorithm=hash_algorithm)
        inventory[rel_path] = info

        # Update cache with new result
        if cache is not None and not info.error:
            try:
                st = os.stat(abs_path)
                cache.store(
                    rel_path, st.st_size, st.st_mtime,
                    info.content_hash, info.is_binary,
                    info.line_count, info.word_count, info.char_count,
                    info.version_strings,
                )
            except OSError:
                pass

        if throttle and total > 0:
            throttle.update(
                (idx + 1) / total,
                f"Hashing: {idx + 1:,}/{total:,} files",
            )

    if cache is not None:
        cache.save()

    return inventory


def compute_merkle_hash(
    inventory: dict[str, "FileInfo"],
    hash_algorithm: str = "md5",
) -> str:
    """Compute a single Merkle-style directory fingerprint.

    Sorts all (rel_path, content_hash) pairs, concatenates them with
    null-byte separators, and hashes the result.

    Returns the hex digest, or an empty string if the inventory is empty.
    """
    if not inventory:
        return ""
    hasher = hashlib.new(hash_algorithm)
    for rel_path in sorted(inventory.keys()):
        fi = inventory[rel_path]
        hasher.update(rel_path.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update((fi.content_hash or "").encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# Version String Comparison
# ---------------------------------------------------------------------------

def parse_version(v: str) -> tuple:
    """Parse a version string like '1.2.3' or '2024-01-15' into a comparable tuple."""
    parts = []
    for p in v.split('.'):
        for sub in p.split('-'):
            try:
                parts.append(int(sub))
            except ValueError:
                parts.append(0)
    return tuple(parts)


def compare_version_lists(left_versions: list[str], right_versions: list[str]) -> int:
    """Compare two lists of version strings.

    Returns: negative if left has higher versions, positive if right does, 0 if tie.
    """
    left_max = max((parse_version(v) for v in left_versions), default=())
    right_max = max((parse_version(v) for v in right_versions), default=())
    if not left_max and not right_max:
        return 0
    if not left_max:
        return 1
    if not right_max:
        return -1
    if right_max > left_max:
        return 1
    if left_max > right_max:
        return -1
    return 0


# ---------------------------------------------------------------------------
# Git Commit Counting (Optional Bonus)
# ---------------------------------------------------------------------------

def count_git_commits(dir_path: str) -> Optional[int]:
    """Count git commits if the directory is inside a git repo."""
    try:
        result = subprocess.run(
            ['git', 'rev-list', '--count', 'HEAD'],
            cwd=dir_path,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


# ---------------------------------------------------------------------------
# Core Comparison Logic
# ---------------------------------------------------------------------------

def compare_directories(
    left_dir: str,
    right_dir: str,
    ignore_patterns: list[str],
    weights: Optional[ScoringWeights] = None,
    use_gitignore: bool = False,
    progress_callback=None,
    cancel_event: Optional[threading.Event] = None,
    hash_algorithm: str = "md5",
    plugins_enabled: bool = True,
    plugin_dirs: Optional[list[str]] = None,
    use_cache: bool = False,
) -> ComparisonResult:
    """Compare two directories and produce a full comparison result."""
    if weights is None:
        weights = ScoringWeights()

    # Merge .gitignore patterns if requested
    effective_patterns = list(ignore_patterns)
    if use_gitignore:
        effective_patterns.extend(parse_gitignore(left_dir))
        effective_patterns.extend(parse_gitignore(right_dir))
        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for p in effective_patterns:
            if p not in seen:
                seen.add(p)
                deduped.append(p)
        effective_patterns = deduped

    def _safe_progress(fraction, message=""):
        """Call progress_callback, handling old-style callbacks that only take fraction."""
        if not progress_callback:
            return
        try:
            progress_callback(fraction, message)
        except TypeError:
            progress_callback(fraction)

    def left_progress(fraction, message=""):
        _safe_progress(fraction * 0.45, f"Left: {message}" if message else "")

    def right_progress(fraction, message=""):
        _safe_progress(0.45 + fraction * 0.45, f"Right: {message}" if message else "")

    # Scan both directories in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        left_future = pool.submit(
            scan_directory, left_dir, effective_patterns, left_progress,
            cancel_event, use_gitignore, hash_algorithm, use_cache,
        )
        right_future = pool.submit(
            scan_directory, right_dir, effective_patterns, right_progress,
            cancel_event, use_gitignore, hash_algorithm, use_cache,
        )
        left_inv = left_future.result()
        if cancel_event and cancel_event.is_set():
            return _empty_result(left_dir, right_dir, weights)
        right_inv = right_future.result()
        if cancel_event and cancel_event.is_set():
            return _empty_result(left_dir, right_dir, weights)

    # Compute Merkle directory fingerprints
    left_merkle = compute_merkle_hash(left_inv, hash_algorithm)
    right_merkle = compute_merkle_hash(right_inv, hash_algorithm)

    # Fast path: if Merkle hashes match, directories are content-identical
    if left_merkle and right_merkle and left_merkle == right_merkle:
        all_paths = sorted(left_inv.keys())
        rows = [
            ComparisonRow(
                rel_path=rp,
                status=FileStatus.IDENTICAL,
                size_left=left_inv[rp].size,
                size_right=right_inv[rp].size,
                notes="",
                left_path=left_inv[rp].abs_path,
                right_path=right_inv[rp].abs_path,
            )
            for rp in all_paths
        ]
        status_counts = {s.value: 0 for s in FileStatus}
        status_counts[FileStatus.IDENTICAL.value] = len(all_paths)

        left_total_size = sum(f.size for f in left_inv.values())
        right_total_size = sum(f.size for f in right_inv.values())
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        ext_counter: Counter = Counter()
        for rp in all_paths:
            ext = os.path.splitext(rp)[1].lower() or "(no ext)"
            ext_counter[ext] += 1
        file_type_counts = dict(ext_counter.most_common())

        _safe_progress(1.0, "Done")

        return ComparisonResult(
            left_dir=left_dir,
            right_dir=right_dir,
            left_file_count=len(left_inv),
            right_file_count=len(right_inv),
            left_total_size=left_total_size,
            right_total_size=right_total_size,
            left_versions=[],
            right_versions=[],
            score=0,
            confidence="High",
            explanation="Directories are content-identical (Merkle hash match).",
            rows=rows,
            warnings=[],
            weights=weights,
            status_counts=status_counts,
            timestamp=timestamp,
            file_type_counts=file_type_counts,
            score_breakdown={},
            left_merkle_hash=left_merkle,
            right_merkle_hash=right_merkle,
        )

    all_paths = sorted(set(left_inv.keys()) | set(right_inv.keys()))

    rows: list[ComparisonRow] = []
    warnings: list[str] = []
    score = 0
    content_heuristic_used = 0

    all_left_versions: list[str] = []
    all_right_versions: list[str] = []
    status_counts = {s: 0 for s in FileStatus}

    for rel_path in all_paths:
        if cancel_event and cancel_event.is_set():
            break

        left_file = left_inv.get(rel_path)
        right_file = right_inv.get(rel_path)

        if left_file and left_file.version_strings:
            all_left_versions.extend(left_file.version_strings)
        if right_file and right_file.version_strings:
            all_right_versions.extend(right_file.version_strings)

        if left_file and not right_file:
            rows.append(ComparisonRow(
                rel_path=rel_path, status=FileStatus.LEFT_ONLY,
                size_left=left_file.size, size_right=None,
                notes=left_file.error or "",
                left_path=left_file.abs_path, right_path=None,
            ))
            score -= weights.unique_file
            status_counts[FileStatus.LEFT_ONLY] += 1

        elif right_file and not left_file:
            rows.append(ComparisonRow(
                rel_path=rel_path, status=FileStatus.RIGHT_ONLY,
                size_left=None, size_right=right_file.size,
                notes=right_file.error or "",
                left_path=None, right_path=right_file.abs_path,
            ))
            score += weights.unique_file
            status_counts[FileStatus.RIGHT_ONLY] += 1

        elif left_file and right_file:
            if left_file.error or right_file.error:
                notes_parts = []
                if left_file.error:
                    notes_parts.append(f"Left: {left_file.error}")
                if right_file.error:
                    notes_parts.append(f"Right: {right_file.error}")
                rows.append(ComparisonRow(
                    rel_path=rel_path, status=FileStatus.UNKNOWN,
                    size_left=left_file.size, size_right=right_file.size,
                    notes="; ".join(notes_parts),
                    left_path=left_file.abs_path, right_path=right_file.abs_path,
                ))
                status_counts[FileStatus.UNKNOWN] += 1
                continue

            if left_file.content_hash == right_file.content_hash:
                rows.append(ComparisonRow(
                    rel_path=rel_path, status=FileStatus.IDENTICAL,
                    size_left=left_file.size, size_right=right_file.size,
                    notes="",
                    left_path=left_file.abs_path, right_path=right_file.abs_path,
                ))
                status_counts[FileStatus.IDENTICAL] += 1
            else:
                file_score, notes, used_heuristic = _analyze_difference(
                    left_file, right_file,
                )
                if used_heuristic:
                    content_heuristic_used += 1
                if file_score < 0:
                    status = FileStatus.LEFT_NEWER
                    score -= weights.content_analysis
                elif file_score > 0:
                    status = FileStatus.RIGHT_NEWER
                    score += weights.content_analysis
                else:
                    status = FileStatus.UNKNOWN

                status_counts[status] += 1
                rows.append(ComparisonRow(
                    rel_path=rel_path, status=status,
                    size_left=left_file.size, size_right=right_file.size,
                    notes=notes,
                    left_path=left_file.abs_path, right_path=right_file.abs_path,
                ))

    # Global version string bonus
    ver_cmp = compare_version_lists(
        list(set(all_left_versions)), list(set(all_right_versions))
    )
    if ver_cmp > 0:
        score += weights.version_string
    elif ver_cmp < 0:
        score -= weights.version_string

    # Git commit bonus
    left_commits = count_git_commits(left_dir)
    right_commits = count_git_commits(right_dir)
    if left_commits is not None and right_commits is not None:
        if right_commits > left_commits:
            score += weights.git_commits
        elif left_commits > right_commits:
            score -= weights.git_commits

    # Build score breakdown
    score_breakdown: dict[str, int] = {}
    left_unique_pts = -weights.unique_file * status_counts.get(FileStatus.LEFT_ONLY, 0)
    right_unique_pts = weights.unique_file * status_counts.get(FileStatus.RIGHT_ONLY, 0)
    unique_pts = left_unique_pts + right_unique_pts
    if unique_pts != 0:
        score_breakdown["unique_files"] = unique_pts

    content_pts = 0
    left_newer_count = status_counts.get(FileStatus.LEFT_NEWER, 0)
    right_newer_count = status_counts.get(FileStatus.RIGHT_NEWER, 0)
    content_pts = (right_newer_count - left_newer_count) * weights.content_analysis
    if content_pts != 0:
        score_breakdown["content_analysis"] = content_pts

    ver_pts = 0
    if ver_cmp > 0:
        ver_pts = weights.version_string
    elif ver_cmp < 0:
        ver_pts = -weights.version_string
    if ver_pts != 0:
        score_breakdown["version_strings"] = ver_pts

    git_pts = 0
    if left_commits is not None and right_commits is not None:
        if right_commits > left_commits:
            git_pts = weights.git_commits
        elif left_commits > right_commits:
            git_pts = -weights.git_commits
    if git_pts != 0:
        score_breakdown["git_commits"] = git_pts

    # Build warnings
    if content_heuristic_used > 0:
        warnings.append(
            f"Content volume heuristic ('more content = newer') was used for "
            f"{content_heuristic_used} file(s). This may not be accurate for "
            f"refactored or simplified code."
        )

    # Build explanation
    explanation_parts = []
    if status_counts.get(FileStatus.LEFT_ONLY, 0):
        explanation_parts.append(
            f"Left has {status_counts[FileStatus.LEFT_ONLY]} unique file(s)"
        )
    if status_counts.get(FileStatus.RIGHT_ONLY, 0):
        explanation_parts.append(
            f"Right has {status_counts[FileStatus.RIGHT_ONLY]} unique file(s)"
        )
    if status_counts.get(FileStatus.LEFT_NEWER, 0):
        explanation_parts.append(
            f"Left has newer content in {status_counts[FileStatus.LEFT_NEWER]} shared file(s)"
        )
    if status_counts.get(FileStatus.RIGHT_NEWER, 0):
        explanation_parts.append(
            f"Right has newer content in {status_counts[FileStatus.RIGHT_NEWER]} shared file(s)"
        )
    if status_counts.get(FileStatus.IDENTICAL, 0):
        explanation_parts.append(
            f"{status_counts[FileStatus.IDENTICAL]} file(s) are identical"
        )
    if ver_cmp > 0:
        explanation_parts.append("Right has higher version strings")
    elif ver_cmp < 0:
        explanation_parts.append("Left has higher version strings")
    if left_commits is not None and right_commits is not None:
        if right_commits > left_commits:
            explanation_parts.append(
                f"Right has more git commits ({right_commits} vs {left_commits})"
            )
        elif left_commits > right_commits:
            explanation_parts.append(
                f"Left has more git commits ({left_commits} vs {right_commits})"
            )

    explanation = (
        ". ".join(explanation_parts) + "."
        if explanation_parts
        else "No significant differences found."
    )

    # Confidence level
    abs_score = abs(score)
    if abs_score >= 8:
        confidence = "High"
    elif abs_score >= 3:
        confidence = "Medium"
    else:
        confidence = "Low"

    if progress_callback:
        _safe_progress(1.0, "Done")

    left_total_size = sum(f.size for f in left_inv.values())
    right_total_size = sum(f.size for f in right_inv.values())

    # Compute timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Compute file type breakdown
    ext_counter: Counter = Counter()
    for rel_path in all_paths:
        ext = os.path.splitext(rel_path)[1].lower() or "(no ext)"
        ext_counter[ext] += 1
    file_type_counts = dict(ext_counter.most_common())

    # Run plugins
    from .plugins import discover_plugins, run_plugins
    loaded_plugins = discover_plugins(
        extra_dirs=plugin_dirs, enabled=plugins_enabled,
    )
    if loaded_plugins:
        plugin_score, plugin_breakdown, plugin_warnings = run_plugins(
            loaded_plugins, left_inv, right_inv,
        )
        score += plugin_score
        score_breakdown.update(plugin_breakdown)
        warnings.extend(plugin_warnings)

    return ComparisonResult(
        left_dir=left_dir,
        right_dir=right_dir,
        left_file_count=len(left_inv),
        right_file_count=len(right_inv),
        left_total_size=left_total_size,
        right_total_size=right_total_size,
        left_versions=sorted(set(all_left_versions)),
        right_versions=sorted(set(all_right_versions)),
        score=score,
        confidence=confidence,
        explanation=explanation,
        rows=rows,
        warnings=warnings,
        weights=weights,
        left_git_commits=left_commits,
        right_git_commits=right_commits,
        status_counts={s.value: c for s, c in status_counts.items()},
        timestamp=timestamp,
        file_type_counts=file_type_counts,
        score_breakdown=score_breakdown,
        left_merkle_hash=left_merkle,
        right_merkle_hash=right_merkle,
    )


def _analyze_difference(left: FileInfo, right: FileInfo) -> tuple[int, str, bool]:
    """Analyze difference between two files with different hashes.

    Returns (file_score, notes, used_content_heuristic) where:
        - negative file_score = left is newer
        - positive file_score = right is newer
        - used_content_heuristic = True if the "more content = newer" heuristic was applied
    """
    notes_parts = []
    file_score = 0
    used_heuristic = False

    if not left.is_binary and not right.is_binary:
        # Text file: compare content volume
        left_volume = left.line_count + left.word_count
        right_volume = right.line_count + right.word_count

        if right_volume > left_volume * 1.1:
            file_score += 1
            used_heuristic = True
            notes_parts.append(
                f"Right has more content ({right.line_count}L/{right.word_count}W "
                f"vs {left.line_count}L/{left.word_count}W)"
            )
        elif left_volume > right_volume * 1.1:
            file_score -= 1
            used_heuristic = True
            notes_parts.append(
                f"Left has more content ({left.line_count}L/{left.word_count}W "
                f"vs {right.line_count}L/{right.word_count}W)"
            )
        else:
            notes_parts.append("Similar content volume, different content")

        # Per-file version string comparison
        ver_cmp = compare_version_lists(left.version_strings, right.version_strings)
        if ver_cmp > 0:
            file_score += 2
            notes_parts.append("Version string higher on right")
        elif ver_cmp < 0:
            file_score -= 2
            notes_parts.append("Version string higher on left")
    else:
        # Binary file: size tiebreaker
        if right.size > left.size:
            file_score += 1
            notes_parts.append(
                f"Right is larger ({fmt_size(right.size)} vs {fmt_size(left.size)})"
            )
        elif left.size > right.size:
            file_score -= 1
            notes_parts.append(
                f"Left is larger ({fmt_size(left.size)} vs {fmt_size(right.size)})"
            )
        else:
            notes_parts.append("Same size, different content")

    return file_score, "; ".join(notes_parts), used_heuristic


def _empty_result(left_dir: str, right_dir: str, weights: ScoringWeights) -> ComparisonResult:
    return ComparisonResult(
        left_dir=left_dir, right_dir=right_dir,
        left_file_count=0, right_file_count=0,
        left_total_size=0, right_total_size=0,
        left_versions=[], right_versions=[],
        score=0, confidence="Low",
        explanation="Comparison cancelled.",
        rows=[], warnings=[], weights=weights,
        status_counts={},
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        file_type_counts={},
        score_breakdown={},
        left_merkle_hash="",
        right_merkle_hash="",
    )


# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------

def fmt_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# ---------------------------------------------------------------------------
# Export Functions
# ---------------------------------------------------------------------------

def _verdict_text(score: int) -> str:
    if score < 0:
        return "LEFT is more up to date"
    elif score > 0:
        return "RIGHT is more up to date"
    return "Both directories appear equivalent"


def export_report_txt(result: ComparisonResult) -> str:
    """Generate a plain-text report."""
    lines = []
    lines.append("=" * 78)
    lines.append("DirCompare Report")
    lines.append("=" * 78)
    lines.append(f"Generated: {result.timestamp}")
    lines.append(f"Left:  {result.left_dir}")
    lines.append(f"Right: {result.right_dir}")
    lines.append("")
    lines.append(f"Left:  {result.left_file_count} files, {fmt_size(result.left_total_size)}")
    lines.append(f"Right: {result.right_file_count} files, {fmt_size(result.right_total_size)}")
    lines.append("")
    if result.left_versions:
        lines.append(f"Left version strings:  {', '.join(result.left_versions)}")
    if result.right_versions:
        lines.append(f"Right version strings: {', '.join(result.right_versions)}")
    if result.left_versions or result.right_versions:
        lines.append("")

    if result.left_merkle_hash and result.right_merkle_hash:
        if result.left_merkle_hash == result.right_merkle_hash:
            lines.append("Merkle hash match: directories are content-identical")
        else:
            lines.append(f"Left Merkle hash:  {result.left_merkle_hash}")
            lines.append(f"Right Merkle hash: {result.right_merkle_hash}")
        lines.append("")

    lines.append(f"VERDICT: {_verdict_text(result.score)}")
    lines.append(f"Confidence: {result.confidence} (score: {result.score})")
    lines.append(f"Weights: unique={result.weights.unique_file}, "
                 f"content={result.weights.content_analysis}, "
                 f"version={result.weights.version_string}, "
                 f"git={result.weights.git_commits}")
    lines.append(f"Explanation: {result.explanation}")
    if result.score_breakdown:
        parts = [f"{k}={v:+d}" for k, v in result.score_breakdown.items()]
        lines.append(f"Score breakdown: {', '.join(parts)}")

    if result.warnings:
        lines.append("")
        for w in result.warnings:
            lines.append(f"WARNING: {w}")

    lines.append("")
    lines.append("-" * 78)
    lines.append(
        f"{'Relative Path':<45} {'Status':<14} {'Size L':>10} {'Size R':>10}  Notes"
    )
    lines.append("-" * 78)

    for row in result.rows:
        sl = fmt_size(row.size_left) if row.size_left is not None else "-"
        sr = fmt_size(row.size_right) if row.size_right is not None else "-"
        path_display = (
            row.rel_path if len(row.rel_path) <= 44
            else "..." + row.rel_path[-41:]
        )
        lines.append(
            f"{path_display:<45} {row.status.value:<14} {sl:>10} {sr:>10}  {row.notes}"
        )

    lines.append("")
    return "\n".join(lines)


def export_report_csv(result: ComparisonResult) -> str:
    """Generate a CSV report."""
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(["# Generated", result.timestamp, "", "", ""])
    writer.writerow(["Relative Path", "Status", "Size Left", "Size Right", "Notes"])
    for row in result.rows:
        writer.writerow([
            row.rel_path,
            row.status.value,
            row.size_left if row.size_left is not None else "",
            row.size_right if row.size_right is not None else "",
            row.notes,
        ])
    return output.getvalue()


def export_report_json(result: ComparisonResult) -> str:
    """Generate a JSON report."""
    data = {
        "timestamp": result.timestamp,
        "left_dir": result.left_dir,
        "right_dir": result.right_dir,
        "left_file_count": result.left_file_count,
        "right_file_count": result.right_file_count,
        "left_total_size": result.left_total_size,
        "right_total_size": result.right_total_size,
        "left_versions": result.left_versions,
        "right_versions": result.right_versions,
        "score": result.score,
        "confidence": result.confidence,
        "verdict": _verdict_text(result.score),
        "explanation": result.explanation,
        "warnings": result.warnings,
        "weights": {
            "unique_file": result.weights.unique_file,
            "content_analysis": result.weights.content_analysis,
            "version_string": result.weights.version_string,
            "git_commits": result.weights.git_commits,
        },
        "left_git_commits": result.left_git_commits,
        "right_git_commits": result.right_git_commits,
        "status_counts": result.status_counts,
        "score_breakdown": result.score_breakdown,
        "left_merkle_hash": result.left_merkle_hash,
        "right_merkle_hash": result.right_merkle_hash,
        "directories_identical": (
            bool(result.left_merkle_hash)
            and result.left_merkle_hash == result.right_merkle_hash
        ),
        "files": [
            {
                "path": row.rel_path,
                "status": row.status.value,
                "size_left": row.size_left,
                "size_right": row.size_right,
                "notes": row.notes,
            }
            for row in result.rows
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def export_report_html(result: ComparisonResult) -> str:
    """Generate a self-contained HTML report with colour-coded rows."""
    status_colors = {
        "Left Only": "#ffffcc",
        "Right Only": "#cce5ff",
        "Identical": "#d4edda",
        "Left Newer": "#ffe0b2",
        "Right Newer": "#b3e5fc",
        "Unknown": "#e0e0e0",
    }

    verdict = _verdict_text(result.score)
    if result.score < 0:
        verdict_color = "#28a745"
    elif result.score > 0:
        verdict_color = "#007bff"
    else:
        verdict_color = "#6c757d"

    # Build file type breakdown string
    ft_parts = []
    for ext, count in sorted(result.file_type_counts.items(), key=lambda x: -x[1]):
        ft_parts.append(f"{count} {ext}")
    file_types_str = ", ".join(ft_parts[:15])  # Top 15

    # Escape HTML helper
    import html as html_mod
    esc = html_mod.escape

    rows_html = []
    for row in result.rows:
        bg = status_colors.get(row.status.value, "#ffffff")
        sl = fmt_size(row.size_left) if row.size_left is not None else "-"
        sr = fmt_size(row.size_right) if row.size_right is not None else "-"
        rows_html.append(
            f'<tr style="background:{bg}">'
            f'<td>{esc(row.rel_path)}</td>'
            f'<td style="text-align:center">{esc(row.status.value)}</td>'
            f'<td style="text-align:right">{esc(sl)}</td>'
            f'<td style="text-align:right">{esc(sr)}</td>'
            f'<td>{esc(row.notes)}</td>'
            f'</tr>'
        )

    warnings_html = ""
    if result.warnings:
        items = "".join(f"<li>{esc(w)}</li>" for w in result.warnings)
        warnings_html = f'<div class="warnings"><strong>Warnings:</strong><ul>{items}</ul></div>'

    timestamp_line = f"<p><strong>Generated:</strong> {esc(result.timestamp)}</p>" if result.timestamp else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DirCompare Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; color: #333; }}
  h1 {{ border-bottom: 2px solid #333; padding-bottom: 8px; }}
  .summary {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; padding: 16px; margin-bottom: 20px; }}
  .verdict {{ font-size: 1.3em; font-weight: bold; color: {verdict_color}; margin: 8px 0; }}
  .warnings {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 10px; margin-top: 12px; }}
  .warnings ul {{ margin: 4px 0; padding-left: 20px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 16px; font-size: 0.9em; }}
  th {{ background: #343a40; color: white; padding: 8px 10px; text-align: left; position: sticky; top: 0; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid #dee2e6; }}
  tr:hover {{ filter: brightness(0.95); }}
  .meta {{ color: #666; font-size: 0.85em; }}
</style>
</head>
<body>
<h1>DirCompare Report</h1>
{timestamp_line}
<div class="summary">
  <p><strong>Left:</strong> {esc(result.left_dir)} &mdash; {result.left_file_count} files, {fmt_size(result.left_total_size)}</p>
  <p><strong>Right:</strong> {esc(result.right_dir)} &mdash; {result.right_file_count} files, {fmt_size(result.right_total_size)}</p>
  <p class="verdict">{esc(verdict)}</p>
  <p><strong>Confidence:</strong> {result.confidence} (score: {result.score})</p>
  <p><strong>Weights:</strong> unique={result.weights.unique_file}, content={result.weights.content_analysis}, version={result.weights.version_string}, git={result.weights.git_commits}</p>
  <p><strong>Explanation:</strong> {esc(result.explanation)}</p>
  {"<p><strong>Score breakdown:</strong> " + esc(", ".join(f"{k}={v:+d}" for k, v in result.score_breakdown.items())) + "</p>" if result.score_breakdown else ""}
  {"<p><strong>File types:</strong> " + esc(file_types_str) + "</p>" if file_types_str else ""}
  {"<p><strong>Merkle hash:</strong> directories are content-identical</p>" if result.left_merkle_hash and result.left_merkle_hash == result.right_merkle_hash else ("<p><strong>Left Merkle:</strong> " + esc(result.left_merkle_hash) + " | <strong>Right Merkle:</strong> " + esc(result.right_merkle_hash) + "</p>" if result.left_merkle_hash else "")}
  {warnings_html}
</div>
<table>
<thead>
<tr><th>Relative Path</th><th>Status</th><th>Size Left</th><th>Size Right</th><th>Notes</th></tr>
</thead>
<tbody>
{"".join(rows_html)}
</tbody>
</table>
</body>
</html>"""
