"""Tests for the comparison history module."""

import json
import os
import tempfile
import unittest

from DirCompare.history import HistoryManager


class TestHistoryManager(unittest.TestCase):
    """Tests for HistoryManager."""

    def setUp(self):
        self.tmpfile = tempfile.mktemp(suffix=".json")
        self.mgr = HistoryManager(path=self.tmpfile, max_entries=5)

    def tearDown(self):
        if os.path.exists(self.tmpfile):
            os.remove(self.tmpfile)

    def test_load_empty(self):
        """Loading when no file exists returns empty list."""
        self.assertEqual(self.mgr.load(), [])

    def test_save_and_load(self):
        """Saving an entry and loading it back should round-trip."""
        entry = {"timestamp": "2026-01-01 12:00:00", "left_dir": "/a", "right_dir": "/b", "score": -3}
        self.mgr.save_entry(entry)
        entries = self.mgr.load()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["score"], -3)

    def test_newest_first(self):
        """Newest entries should appear first."""
        self.mgr.save_entry({"score": 1})
        self.mgr.save_entry({"score": 2})
        self.mgr.save_entry({"score": 3})
        entries = self.mgr.load()
        self.assertEqual([e["score"] for e in entries], [3, 2, 1])

    def test_max_entries_trimming(self):
        """Exceeding max_entries should trim oldest entries."""
        for i in range(10):
            self.mgr.save_entry({"index": i})
        entries = self.mgr.load()
        self.assertEqual(len(entries), 5)
        # Newest should be index 9
        self.assertEqual(entries[0]["index"], 9)

    def test_clear(self):
        """Clearing should remove all history."""
        self.mgr.save_entry({"score": 1})
        self.mgr.clear()
        self.assertEqual(self.mgr.load(), [])

    def test_clear_nonexistent(self):
        """Clearing when no file exists should not error."""
        self.mgr.clear()  # Should not raise

    def test_corrupt_file_handling(self):
        """Loading a corrupt JSON file should return empty list."""
        with open(self.tmpfile, "w") as f:
            f.write("not valid json{{{")
        self.assertEqual(self.mgr.load(), [])

    def test_non_list_json(self):
        """Loading a JSON file that is not a list should return empty list."""
        with open(self.tmpfile, "w") as f:
            json.dump({"key": "value"}, f)
        self.assertEqual(self.mgr.load(), [])

    def test_format_history_empty(self):
        """format_history with no entries should show 'No comparison history.'"""
        result = self.mgr.format_history()
        self.assertIn("No comparison history", result)

    def test_format_history_with_entries(self):
        """format_history should include entry details."""
        self.mgr.save_entry({
            "timestamp": "2026-01-15 10:00:00",
            "left_dir": "/path/left",
            "right_dir": "/path/right",
            "verdict": "LEFT is more up to date",
            "score": -5,
            "confidence": "High",
        })
        result = self.mgr.format_history()
        self.assertIn("/path/left", result)
        self.assertIn("LEFT is more up to date", result)

    def test_make_entry_left_newer(self):
        """make_entry with negative score should say LEFT is more up to date."""
        class FakeResult:
            timestamp = "2026-01-01"
            left_dir = "/a"
            right_dir = "/b"
            score = -3
            confidence = "Medium"
            left_file_count = 10
            right_file_count = 8
        entry = HistoryManager.make_entry(FakeResult())
        self.assertEqual(entry["verdict"], "LEFT is more up to date")

    def test_make_entry_right_newer(self):
        """make_entry with positive score should say RIGHT is more up to date."""
        class FakeResult:
            timestamp = "2026-01-01"
            left_dir = "/a"
            right_dir = "/b"
            score = 5
            confidence = "High"
            left_file_count = 10
            right_file_count = 12
        entry = HistoryManager.make_entry(FakeResult())
        self.assertEqual(entry["verdict"], "RIGHT is more up to date")

    def test_make_entry_equivalent(self):
        """make_entry with zero score should say equivalent."""
        class FakeResult:
            timestamp = "2026-01-01"
            left_dir = "/a"
            right_dir = "/b"
            score = 0
            confidence = "Low"
            left_file_count = 5
            right_file_count = 5
        entry = HistoryManager.make_entry(FakeResult())
        self.assertEqual(entry["verdict"], "Directories are equivalent")


if __name__ == "__main__":
    unittest.main()
