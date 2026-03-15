"""
DirCompare hash cache.

Persists per-file hashes to disk so repeated comparisons can skip
re-reading unchanged files.  Uses (rel_path, size, mtime) as the cache key.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_FILENAME = ".dircompare_cache.json"
CACHE_VERSION = 1


class HashCache:
    """Read/write a per-directory hash cache file."""

    def __init__(self, dir_path: str, hash_algorithm: str = "md5"):
        self._dir_path = os.path.realpath(dir_path)
        self._hash_algorithm = hash_algorithm
        self._cache_path = os.path.join(self._dir_path, CACHE_FILENAME)
        self._entries: dict[str, dict] = {}
        self._dirty = False

    def load(self) -> None:
        """Load cache from disk.  Silently returns empty on any error."""
        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if (
                isinstance(data, dict)
                and data.get("version") == CACHE_VERSION
                and data.get("hash_algorithm") == self._hash_algorithm
            ):
                self._entries = data.get("entries", {})
            else:
                self._entries = {}
        except (OSError, ValueError, json.JSONDecodeError):
            self._entries = {}

    def lookup(self, rel_path: str, size: int, mtime: float) -> Optional[dict]:
        """Look up a cached entry.  Returns dict of cached fields or None."""
        entry = self._entries.get(rel_path)
        if entry is None:
            return None
        if entry.get("size") == size and entry.get("mtime") == mtime:
            return entry
        return None

    def store(
        self,
        rel_path: str,
        size: int,
        mtime: float,
        content_hash: str,
        is_binary: bool,
        line_count: int,
        word_count: int,
        char_count: int,
        version_strings: list[str],
    ) -> None:
        """Store a file's scan results in the cache."""
        self._entries[rel_path] = {
            "size": size,
            "mtime": mtime,
            "content_hash": content_hash,
            "is_binary": is_binary,
            "line_count": line_count,
            "word_count": word_count,
            "char_count": char_count,
            "version_strings": version_strings,
        }
        self._dirty = True

    def save(self) -> None:
        """Write cache to disk.  Silently ignores write errors."""
        if not self._dirty:
            return
        data = {
            "version": CACHE_VERSION,
            "hash_algorithm": self._hash_algorithm,
            "entries": self._entries,
        }
        try:
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            logger.debug("Could not write cache to %s", self._cache_path)

    @property
    def cache_path(self) -> str:
        return self._cache_path
