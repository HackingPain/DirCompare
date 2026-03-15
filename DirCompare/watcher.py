"""
Directory watcher for DirCompare.
Polls directories for file changes using os.walk + os.stat (stdlib only).
"""

import os
import time
from typing import Optional

from .engine import should_ignore


class DirectoryWatcher:
    """Poll-based directory change detector.

    Takes a snapshot of file mtimes and sizes, then detects changes
    on subsequent calls to ``has_changes()``.
    """

    def __init__(self, dir_path: str, ignore_patterns: list[str]):
        self._dir_path = os.path.realpath(dir_path)
        self._ignore_patterns = ignore_patterns
        self._snapshot: dict[str, tuple[float, int]] = {}
        self._take_snapshot()

    def _take_snapshot(self) -> dict[str, tuple[float, int]]:
        """Walk directory and record (mtime, size) for each file."""
        snap: dict[str, tuple[float, int]] = {}
        for root, dirs, files in os.walk(self._dir_path, followlinks=False):
            # Filter ignored directories
            dirs[:] = [
                d for d in dirs
                if not should_ignore(
                    os.path.relpath(os.path.join(root, d), self._dir_path),
                    self._ignore_patterns,
                )
            ]
            for fname in files:
                rel = os.path.relpath(os.path.join(root, fname), self._dir_path)
                rel = rel.replace("\\", "/")
                if should_ignore(rel, self._ignore_patterns):
                    continue
                full_path = os.path.join(root, fname)
                try:
                    st = os.stat(full_path)
                    snap[rel] = (st.st_mtime, st.st_size)
                except OSError:
                    pass
        self._snapshot = snap
        return snap

    def has_changes(self) -> bool:
        """Take a new snapshot and compare with previous.

        Returns True if any files were added, removed, or modified.
        """
        old = self._snapshot
        new = self._take_snapshot()
        return old != new


def watch_and_compare(
    left_dir: str,
    right_dir: str,
    ignore_patterns: list[str],
    interval: float = 5.0,
    run_comparison=None,
    cancel_event=None,
) -> None:
    """Watch two directories and re-run comparison when changes are detected.

    Parameters
    ----------
    left_dir : str
        Path to the left directory.
    right_dir : str
        Path to the right directory.
    ignore_patterns : list[str]
        Patterns for files/dirs to ignore.
    interval : float
        Seconds between polls (default 5.0, minimum 0.5).
    run_comparison : callable, optional
        Function to call when changes are detected (or on initial run).
        If None, a default message is printed.
    cancel_event : threading.Event, optional
        If set, the watch loop exits.
    """
    import sys

    interval = max(0.5, interval)

    left_watcher = DirectoryWatcher(left_dir, ignore_patterns)
    right_watcher = DirectoryWatcher(right_dir, ignore_patterns)

    # Initial comparison
    if run_comparison:
        run_comparison()

    print(
        f"\nWatching for changes (polling every {interval:.1f}s). Press Ctrl+C to stop.",
        file=sys.stderr,
    )

    try:
        while True:
            if cancel_event and cancel_event.is_set():
                break
            time.sleep(interval)
            left_changed = left_watcher.has_changes()
            right_changed = right_watcher.has_changes()
            if left_changed or right_changed:
                which = []
                if left_changed:
                    which.append("left")
                if right_changed:
                    which.append("right")
                print(
                    f"\n--- Changes detected in {' and '.join(which)} directory "
                    f"[{time.strftime('%H:%M:%S')}] ---",
                    file=sys.stderr,
                )
                if run_comparison:
                    run_comparison()
    except KeyboardInterrupt:
        print("\nWatch mode stopped.", file=sys.stderr)
