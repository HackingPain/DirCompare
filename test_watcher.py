"""Tests for the directory watcher module."""

import os
import shutil
import tempfile
import time
import unittest

from DirCompare.watcher import DirectoryWatcher


class TestDirectoryWatcher(unittest.TestCase):
    """Tests for DirectoryWatcher change detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create initial files
        with open(os.path.join(self.tmpdir, "file1.txt"), "w") as f:
            f.write("hello\n")
        with open(os.path.join(self.tmpdir, "file2.txt"), "w") as f:
            f.write("world\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_changes_initially(self):
        """Immediately after creation, has_changes should return False."""
        watcher = DirectoryWatcher(self.tmpdir, [])
        self.assertFalse(watcher.has_changes())

    def test_detect_new_file(self):
        """Adding a new file should be detected as a change."""
        watcher = DirectoryWatcher(self.tmpdir, [])
        with open(os.path.join(self.tmpdir, "new.txt"), "w") as f:
            f.write("new content\n")
        self.assertTrue(watcher.has_changes())

    def test_detect_deleted_file(self):
        """Removing a file should be detected as a change."""
        watcher = DirectoryWatcher(self.tmpdir, [])
        os.remove(os.path.join(self.tmpdir, "file1.txt"))
        self.assertTrue(watcher.has_changes())

    def test_detect_modified_file(self):
        """Modifying a file (changing mtime/size) should be detected."""
        watcher = DirectoryWatcher(self.tmpdir, [])
        # Ensure mtime changes by sleeping briefly
        time.sleep(0.05)
        with open(os.path.join(self.tmpdir, "file1.txt"), "w") as f:
            f.write("modified content that is longer\n")
        self.assertTrue(watcher.has_changes())

    def test_no_change_after_resnapshot(self):
        """After detecting a change, the next call should see no change."""
        watcher = DirectoryWatcher(self.tmpdir, [])
        with open(os.path.join(self.tmpdir, "new.txt"), "w") as f:
            f.write("new\n")
        self.assertTrue(watcher.has_changes())
        # Second call — snapshot is now current
        self.assertFalse(watcher.has_changes())

    def test_ignores_patterns(self):
        """Files matching ignore patterns should not trigger changes."""
        watcher = DirectoryWatcher(self.tmpdir, ["*.log"])
        with open(os.path.join(self.tmpdir, "debug.log"), "w") as f:
            f.write("log entry\n")
        self.assertFalse(watcher.has_changes())

    def test_detect_subdirectory_change(self):
        """Changes in subdirectories should be detected."""
        sub = os.path.join(self.tmpdir, "subdir")
        os.makedirs(sub)
        watcher = DirectoryWatcher(self.tmpdir, [])
        with open(os.path.join(sub, "nested.txt"), "w") as f:
            f.write("nested\n")
        self.assertTrue(watcher.has_changes())

    def test_ignores_subdirectory(self):
        """Ignored subdirectories should not be scanned."""
        watcher = DirectoryWatcher(self.tmpdir, ["__pycache__"])
        cache = os.path.join(self.tmpdir, "__pycache__")
        os.makedirs(cache)
        with open(os.path.join(cache, "module.pyc"), "w") as f:
            f.write("bytecode\n")
        self.assertFalse(watcher.has_changes())

    def test_empty_directory(self):
        """Watching an empty directory should work without error."""
        empty = tempfile.mkdtemp()
        try:
            watcher = DirectoryWatcher(empty, [])
            self.assertFalse(watcher.has_changes())
        finally:
            shutil.rmtree(empty, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
