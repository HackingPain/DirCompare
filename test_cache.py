"""
Unit tests for the DirCompare hash cache module.

Run with:
    python -m pytest test_cache.py
    python -m unittest test_cache.py
"""

import json
import os
import shutil
import tempfile
import unittest

from DirCompare.cache import CACHE_FILENAME, CACHE_VERSION, HashCache
from DirCompare.engine import compare_directories, scan_directory


class TestHashCache(unittest.TestCase):
    """Tests for the HashCache class."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _cache(self, alg="md5"):
        return HashCache(self.tmpdir, alg)

    def test_roundtrip(self):
        """Store an entry, save, reload, and verify lookup succeeds."""
        c = self._cache()
        c.store("a.txt", 100, 1700000000.0, "abc123", False, 10, 20, 80, ["1.0"])
        c.save()

        c2 = self._cache()
        c2.load()
        entry = c2.lookup("a.txt", 100, 1700000000.0)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["content_hash"], "abc123")
        self.assertEqual(entry["is_binary"], False)
        self.assertEqual(entry["line_count"], 10)
        self.assertEqual(entry["word_count"], 20)
        self.assertEqual(entry["char_count"], 80)
        self.assertEqual(entry["version_strings"], ["1.0"])

    def test_miss_on_size_change(self):
        """Lookup returns None when file size changed."""
        c = self._cache()
        c.store("a.txt", 100, 1700000000.0, "abc123", False, 10, 20, 80, [])
        c.save()

        c2 = self._cache()
        c2.load()
        self.assertIsNone(c2.lookup("a.txt", 200, 1700000000.0))

    def test_miss_on_mtime_change(self):
        """Lookup returns None when file mtime changed."""
        c = self._cache()
        c.store("a.txt", 100, 1700000000.0, "abc123", False, 10, 20, 80, [])
        c.save()

        c2 = self._cache()
        c2.load()
        self.assertIsNone(c2.lookup("a.txt", 100, 1700000001.0))

    def test_miss_on_unknown_file(self):
        """Lookup returns None for a file never stored."""
        c = self._cache()
        c.load()
        self.assertIsNone(c.lookup("unknown.txt", 100, 1700000000.0))

    def test_algorithm_change_invalidates(self):
        """Cache saved with md5 is discarded when loaded with sha256."""
        c = self._cache("md5")
        c.store("a.txt", 100, 1700000000.0, "abc123", False, 10, 20, 80, [])
        c.save()

        c2 = self._cache("sha256")
        c2.load()
        self.assertIsNone(c2.lookup("a.txt", 100, 1700000000.0))

    def test_corrupt_file_handled(self):
        """Loading a corrupt cache file does not crash."""
        cache_path = os.path.join(self.tmpdir, CACHE_FILENAME)
        with open(cache_path, "w") as f:
            f.write("{{not valid json}}")

        c = self._cache()
        c.load()  # Should not raise
        self.assertIsNone(c.lookup("a.txt", 100, 1700000000.0))

    def test_missing_file_handled(self):
        """Loading from a non-existent cache file does not crash."""
        c = self._cache()
        c.load()  # Should not raise
        self.assertIsNone(c.lookup("a.txt", 100, 1700000000.0))

    def test_not_dirty_no_write(self):
        """Save does not write file if no entries were stored."""
        c = self._cache()
        c.load()
        c.save()
        cache_path = os.path.join(self.tmpdir, CACHE_FILENAME)
        self.assertFalse(os.path.exists(cache_path))

    def test_scan_directory_creates_cache(self):
        """scan_directory with use_cache=True creates the cache file."""
        with open(os.path.join(self.tmpdir, "hello.txt"), "w") as f:
            f.write("hello world\n")
        scan_directory(self.tmpdir, [], use_cache=True)
        cache_path = os.path.join(self.tmpdir, CACHE_FILENAME)
        self.assertTrue(os.path.exists(cache_path))
        with open(cache_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["version"], CACHE_VERSION)
        self.assertIn("hello.txt", data["entries"])

    def test_cache_file_excluded_from_inventory(self):
        """The .dircompare_cache.json file itself is excluded from scan results."""
        with open(os.path.join(self.tmpdir, "hello.txt"), "w") as f:
            f.write("hello world\n")
        # First scan creates cache
        scan_directory(self.tmpdir, [], use_cache=True)
        # Second scan should not include cache file
        inv = scan_directory(self.tmpdir, [], use_cache=True)
        self.assertNotIn(CACHE_FILENAME, inv)
        self.assertIn("hello.txt", inv)

    def test_compare_directories_with_cache(self):
        """Full end-to-end comparison with use_cache=True works correctly."""
        left = tempfile.mkdtemp()
        right = tempfile.mkdtemp()
        try:
            with open(os.path.join(left, "a.txt"), "w") as f:
                f.write("hello\n")
            with open(os.path.join(right, "a.txt"), "w") as f:
                f.write("hello\n")
            result = compare_directories(left, right, [], use_cache=True)
            self.assertEqual(result.score, 0)
            # Cache files should exist
            self.assertTrue(os.path.exists(os.path.join(left, CACHE_FILENAME)))
            self.assertTrue(os.path.exists(os.path.join(right, CACHE_FILENAME)))
        finally:
            shutil.rmtree(left, ignore_errors=True)
            shutil.rmtree(right, ignore_errors=True)

    def test_cache_disabled_by_default(self):
        """scan_directory without use_cache does not create a cache file."""
        with open(os.path.join(self.tmpdir, "hello.txt"), "w") as f:
            f.write("hello world\n")
        scan_directory(self.tmpdir, [])
        cache_path = os.path.join(self.tmpdir, CACHE_FILENAME)
        self.assertFalse(os.path.exists(cache_path))

    def test_cache_hit_produces_same_inventory(self):
        """A second scan with cache produces the same inventory as without."""
        with open(os.path.join(self.tmpdir, "a.txt"), "w") as f:
            f.write("content\n")
        with open(os.path.join(self.tmpdir, "b.txt"), "w") as f:
            f.write("other\n")

        # First scan populates cache
        inv1 = scan_directory(self.tmpdir, [], use_cache=True)
        # Second scan should use cache
        inv2 = scan_directory(self.tmpdir, [], use_cache=True)

        self.assertEqual(set(inv1.keys()), set(inv2.keys()))
        for key in inv1:
            self.assertEqual(inv1[key].content_hash, inv2[key].content_hash)
            self.assertEqual(inv1[key].is_binary, inv2[key].is_binary)
            self.assertEqual(inv1[key].line_count, inv2[key].line_count)


if __name__ == "__main__":
    unittest.main()
