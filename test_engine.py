"""
Comprehensive unit tests for the DirCompare engine module.

Run with:
    python -m pytest test_engine.py
    python -m unittest test_engine.py
"""

import csv
import io
import json
import os
import platform
import re as re_mod
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest

from DirCompare.engine import (
    ComparisonResult,
    DEFAULT_IGNORE_PATTERNS,
    FileStatus,
    IGNORE_CATEGORIES,
    ProgressThrottle,
    ScoringWeights,
    _flatten_categories,
    _match_pattern,
    _pattern_cache,
    compare_directories,
    compare_version_lists,
    compute_merkle_hash,
    export_report_csv,
    export_report_html,
    export_report_json,
    export_report_txt,
    fmt_size,
    parse_gitignore,
    parse_version,
    scan_directory,
    scan_file,
    should_ignore,
)


class TestShouldIgnore(unittest.TestCase):
    """Tests for the should_ignore function."""

    def test_exact_match(self):
        """An exact filename match should be ignored."""
        self.assertTrue(should_ignore("__pycache__", ["__pycache__"]))

    def test_no_match(self):
        """A path that does not match any pattern should not be ignored."""
        self.assertFalse(should_ignore("main.py", ["__pycache__"]))

    def test_wildcard_star(self):
        """A * wildcard pattern should match filenames."""
        self.assertTrue(should_ignore("module.pyc", ["*.pyc"]))
        self.assertFalse(should_ignore("module.py", ["*.pyc"]))

    def test_wildcard_question(self):
        """A ? wildcard should match exactly one character."""
        self.assertTrue(should_ignore("file1.txt", ["file?.txt"]))
        self.assertFalse(should_ignore("file10.txt", ["file?.txt"]))

    def test_path_component_matching(self):
        """Patterns should match individual path components."""
        self.assertTrue(should_ignore("src/__pycache__/module.cpython.pyc", ["__pycache__"]))
        self.assertTrue(should_ignore("deep/nested/__pycache__/file.pyc", ["__pycache__"]))

    def test_empty_pattern(self):
        """An empty pattern should not match anything."""
        self.assertFalse(should_ignore("anything.py", [""]))
        self.assertFalse(should_ignore("anything.py", ["  "]))

    def test_case_insensitivity(self):
        """Wildcard pattern matching should be case insensitive."""
        # Literal patterns are case-sensitive (exact match via ==)
        self.assertFalse(should_ignore("README.TXT", ["readme.txt"]))
        # But wildcard patterns use re.IGNORECASE
        self.assertTrue(should_ignore("README.TXT", ["*.txt"]))
        self.assertTrue(should_ignore("Makefile.PYC", ["*.pyc"]))

    def test_multiple_patterns(self):
        """Should match if any pattern matches."""
        patterns = ["__pycache__", "*.pyc", ".git"]
        self.assertTrue(should_ignore("__pycache__", patterns))
        self.assertTrue(should_ignore("test.pyc", patterns))
        self.assertTrue(should_ignore(".git", patterns))
        self.assertFalse(should_ignore("main.py", patterns))


class TestMatchPattern(unittest.TestCase):
    """Tests for the _match_pattern helper function."""

    def test_literal_match(self):
        """Literal pattern with no wildcards should match exact text."""
        self.assertTrue(_match_pattern("hello", "hello"))
        self.assertFalse(_match_pattern("hello", "world"))

    def test_single_star(self):
        """Single * should match any characters except path separators."""
        self.assertTrue(_match_pattern("file.py", "*.py"))
        self.assertTrue(_match_pattern("test_file.py", "*.py"))
        self.assertFalse(_match_pattern("dir/file.py", "*.py"))

    def test_double_star(self):
        """Double ** should match across path separators."""
        self.assertTrue(_match_pattern("a/b/c.py", "**c.py"))
        self.assertTrue(_match_pattern("deeply/nested/path/file.txt", "**file.txt"))

    def test_question_mark(self):
        """? should match exactly one non-separator character."""
        self.assertTrue(_match_pattern("a", "?"))
        self.assertTrue(_match_pattern("file1.txt", "file?.txt"))
        self.assertFalse(_match_pattern("file10.txt", "file?.txt"))
        self.assertFalse(_match_pattern("", "?"))

    def test_mixed_patterns(self):
        """Mixed wildcard patterns should work correctly."""
        self.assertTrue(_match_pattern("test_file.py", "test_*.py"))
        self.assertTrue(_match_pattern("a1b.txt", "a?b.*"))
        self.assertTrue(_match_pattern("prefix_anything_suffix", "prefix_*_suffix"))


class TestParseGitignore(unittest.TestCase):
    """Tests for parsing .gitignore files."""

    def setUp(self):
        """Create a temp directory for .gitignore tests."""
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_basic_patterns(self):
        """Should parse basic .gitignore patterns."""
        gitignore = os.path.join(self.tmpdir, ".gitignore")
        with open(gitignore, "w") as f:
            f.write("*.pyc\n__pycache__\n.env\n")
        patterns = parse_gitignore(self.tmpdir)
        self.assertEqual(patterns, ["*.pyc", "__pycache__", ".env"])

    def test_comments_and_blank_lines(self):
        """Should skip comments and blank lines."""
        gitignore = os.path.join(self.tmpdir, ".gitignore")
        with open(gitignore, "w") as f:
            f.write("# This is a comment\n\n*.pyc\n\n# Another comment\n.env\n")
        patterns = parse_gitignore(self.tmpdir)
        self.assertEqual(patterns, ["*.pyc", ".env"])

    def test_negation_skipped(self):
        """Negation patterns (starting with !) should be skipped."""
        gitignore = os.path.join(self.tmpdir, ".gitignore")
        with open(gitignore, "w") as f:
            f.write("*.log\n!important.log\nbuild/\n")
        patterns = parse_gitignore(self.tmpdir)
        self.assertIn("*.log", patterns)
        self.assertIn("build", patterns)  # trailing slash is stripped
        self.assertNotIn("!important.log", patterns)

    def test_trailing_slash_stripped(self):
        """Trailing slashes on directory patterns should be stripped."""
        gitignore = os.path.join(self.tmpdir, ".gitignore")
        with open(gitignore, "w") as f:
            f.write("build/\nnode_modules/\n")
        patterns = parse_gitignore(self.tmpdir)
        self.assertEqual(patterns, ["build", "node_modules"])

    def test_nonexistent_gitignore(self):
        """Should return empty list if no .gitignore exists."""
        patterns = parse_gitignore(self.tmpdir)
        self.assertEqual(patterns, [])

    def test_mixed_content(self):
        """Should handle a realistic .gitignore with mixed content."""
        gitignore = os.path.join(self.tmpdir, ".gitignore")
        with open(gitignore, "w") as f:
            f.write(
                "# Python\n"
                "*.pyc\n"
                "__pycache__/\n"
                "\n"
                "# Node\n"
                "node_modules/\n"
                "!keep_this\n"
                "\n"
                "# IDE\n"
                ".vscode/\n"
            )
        patterns = parse_gitignore(self.tmpdir)
        self.assertEqual(patterns, ["*.pyc", "__pycache__", "node_modules", ".vscode"])


class TestScanFile(unittest.TestCase):
    """Tests for the single-pass file scanner."""

    def setUp(self):
        """Create a temp directory for file scan tests."""
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_text_file(self):
        """Text file should have correct md5, line_count, word_count, char_count, is_binary=False."""
        filepath = os.path.join(self.tmpdir, "hello.txt")
        content = "Hello World\nThis is a test\nThird line\n"
        with open(filepath, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

        info = scan_file(filepath, "hello.txt")

        self.assertFalse(info.is_binary)
        self.assertIsNone(info.error)
        self.assertEqual(info.line_count, 3)
        # "Hello World" = 2, "This is a test" = 4, "Third line" = 2 => total = 8
        self.assertEqual(info.word_count, 8)
        self.assertGreater(info.char_count, 0)
        self.assertEqual(len(info.content_hash), 32)
        self.assertTrue(info.size > 0)

    def test_binary_file(self):
        """Binary file (containing null bytes) should have is_binary=True and md5 computed."""
        filepath = os.path.join(self.tmpdir, "data.bin")
        with open(filepath, "wb") as f:
            f.write(b"\x00\x01\x02\x03\xff\xfe\xfd\x00")

        info = scan_file(filepath, "data.bin")

        self.assertTrue(info.is_binary)
        self.assertIsNone(info.error)
        self.assertEqual(len(info.content_hash), 32)
        self.assertEqual(info.size, 8)

    def test_version_strings_extracted(self):
        """Files with version strings should have them extracted."""
        filepath = os.path.join(self.tmpdir, "config.py")
        content = 'version = 1.2.3\nsome code here\nv2.0.1 released\n'
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        info = scan_file(filepath, "config.py")

        self.assertFalse(info.is_binary)
        self.assertIn("1.2.3", info.version_strings)
        self.assertIn("2.0.1", info.version_strings)

    @unittest.skipIf(
        platform.system() == "Windows",
        "Symlinks require special privileges on Windows",
    )
    def test_broken_symlink(self):
        """Broken symlinks should report error='broken symlink'."""
        target = os.path.join(self.tmpdir, "nonexistent_target")
        link = os.path.join(self.tmpdir, "broken_link")
        os.symlink(target, link)

        info = scan_file(link, "broken_link")

        self.assertEqual(info.error, "broken symlink")

    @unittest.skipIf(
        platform.system() == "Windows",
        "Permission tests are unreliable on Windows",
    )
    def test_permission_denied(self):
        """Unreadable files should report a permission error."""
        filepath = os.path.join(self.tmpdir, "secret.txt")
        with open(filepath, "w") as f:
            f.write("secret data")
        os.chmod(filepath, 0o000)

        try:
            info = scan_file(filepath, "secret.txt")
            self.assertIsNotNone(info.error)
            self.assertIn("permission", info.error.lower())
        finally:
            # Restore permissions for cleanup
            os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)

    def test_empty_file(self):
        """Empty file should scan without error."""
        filepath = os.path.join(self.tmpdir, "empty.txt")
        with open(filepath, "w") as f:
            pass

        info = scan_file(filepath, "empty.txt")

        self.assertFalse(info.is_binary)
        self.assertIsNone(info.error)
        self.assertEqual(info.size, 0)
        self.assertEqual(info.line_count, 0)
        self.assertEqual(info.word_count, 0)
        self.assertEqual(info.content_hash, "d41d8cd98f00b204e9800998ecf8427e")  # MD5 of empty


class TestParseVersion(unittest.TestCase):
    """Tests for the parse_version function."""

    def test_semver(self):
        """Standard semver '1.2.3' should parse to (1, 2, 3)."""
        self.assertEqual(parse_version("1.2.3"), (1, 2, 3))

    def test_date_version(self):
        """Date-style version '2024-01-15' should parse to (2024, 1, 15)."""
        self.assertEqual(parse_version("2024-01-15"), (2024, 1, 15))

    def test_two_part_version(self):
        """Two-part version '1.0' should parse to (1, 0)."""
        self.assertEqual(parse_version("1.0"), (1, 0))

    def test_four_part_version(self):
        """Four-part version should parse all parts."""
        self.assertEqual(parse_version("1.2.3.4"), (1, 2, 3, 4))

    def test_zero_version(self):
        """Version '0.0.0' should parse correctly."""
        self.assertEqual(parse_version("0.0.0"), (0, 0, 0))


class TestCompareVersionLists(unittest.TestCase):
    """Tests for comparing lists of version strings."""

    def test_left_higher(self):
        """Left having higher versions should return negative."""
        result = compare_version_lists(["2.0.0"], ["1.0.0"])
        self.assertLess(result, 0)

    def test_right_higher(self):
        """Right having higher versions should return positive."""
        result = compare_version_lists(["1.0.0"], ["2.0.0"])
        self.assertGreater(result, 0)

    def test_equal_versions(self):
        """Equal versions should return 0."""
        result = compare_version_lists(["1.0.0"], ["1.0.0"])
        self.assertEqual(result, 0)

    def test_left_empty(self):
        """Empty left list means right wins (positive)."""
        result = compare_version_lists([], ["1.0.0"])
        self.assertGreater(result, 0)

    def test_right_empty(self):
        """Empty right list means left wins (negative)."""
        result = compare_version_lists(["1.0.0"], [])
        self.assertLess(result, 0)

    def test_both_empty(self):
        """Both empty should return 0."""
        result = compare_version_lists([], [])
        self.assertEqual(result, 0)

    def test_multiple_versions_uses_max(self):
        """Should compare the max version from each side."""
        result = compare_version_lists(["1.0.0", "3.0.0"], ["2.0.0", "2.5.0"])
        self.assertLess(result, 0)  # Left max 3.0.0 > right max 2.5.0


class TestCompareDirectories(unittest.TestCase):
    """Integration tests for the directory comparison engine."""

    def setUp(self):
        """Create two temp directories for comparison tests."""
        self.left_dir = tempfile.mkdtemp()
        self.right_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directories."""
        shutil.rmtree(self.left_dir, ignore_errors=True)
        shutil.rmtree(self.right_dir, ignore_errors=True)

    def _write(self, base_dir: str, rel_path: str, content: str) -> None:
        """Helper to write a file inside a temp directory."""
        full_path = os.path.join(base_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    def test_identical_directories(self):
        """Two identical directories should produce score=0 with IDENTICAL statuses."""
        self._write(self.left_dir, "file.txt", "same content\n")
        self._write(self.right_dir, "file.txt", "same content\n")

        result = compare_directories(self.left_dir, self.right_dir, [])

        self.assertEqual(result.score, 0)
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0].status, FileStatus.IDENTICAL)
        self.assertIn("Identical", result.status_counts)

    def test_left_only_files(self):
        """Files only in left should be LEFT_ONLY and push score negative."""
        self._write(self.left_dir, "unique.txt", "only in left\n")

        result = compare_directories(self.left_dir, self.right_dir, [])

        self.assertLess(result.score, 0)
        left_only_rows = [r for r in result.rows if r.status == FileStatus.LEFT_ONLY]
        self.assertEqual(len(left_only_rows), 1)
        self.assertEqual(left_only_rows[0].rel_path, "unique.txt")

    def test_right_only_files(self):
        """Files only in right should be RIGHT_ONLY and push score positive."""
        self._write(self.right_dir, "unique.txt", "only in right\n")

        result = compare_directories(self.left_dir, self.right_dir, [])

        self.assertGreater(result.score, 0)
        right_only_rows = [r for r in result.rows if r.status == FileStatus.RIGHT_ONLY]
        self.assertEqual(len(right_only_rows), 1)

    def test_different_content(self):
        """Files with different content should be detected as different."""
        self._write(self.left_dir, "code.py", "print('hello')\n")
        self._write(self.right_dir, "code.py", "print('hello')\nprint('world')\nprint('extra lines here')\n")

        result = compare_directories(self.left_dir, self.right_dir, [])

        non_identical = [r for r in result.rows if r.status != FileStatus.IDENTICAL]
        self.assertGreater(len(non_identical), 0)

    def test_version_string_difference(self):
        """Files with different version strings should affect scoring."""
        self._write(self.left_dir, "setup.py", '__version__ = "1.0.0"\n')
        self._write(self.right_dir, "setup.py", '__version__ = "2.0.0"\n')

        result = compare_directories(self.left_dir, self.right_dir, [])

        # Right has higher version, score should be positive
        self.assertGreater(result.score, 0)
        self.assertIn("version", result.explanation.lower())

    def test_row_count_and_statuses(self):
        """Verify correct row count and status distribution."""
        self._write(self.left_dir, "same.txt", "identical\n")
        self._write(self.right_dir, "same.txt", "identical\n")
        self._write(self.left_dir, "left_only.txt", "only left\n")
        self._write(self.right_dir, "right_only.txt", "only right\n")

        result = compare_directories(self.left_dir, self.right_dir, [])

        self.assertEqual(len(result.rows), 3)
        statuses = [r.status for r in result.rows]
        self.assertIn(FileStatus.IDENTICAL, statuses)
        self.assertIn(FileStatus.LEFT_ONLY, statuses)
        self.assertIn(FileStatus.RIGHT_ONLY, statuses)

    def test_explanation_text(self):
        """Explanation should describe the differences found."""
        self._write(self.left_dir, "a.txt", "content\n")
        self._write(self.right_dir, "b.txt", "content\n")

        result = compare_directories(self.left_dir, self.right_dir, [])

        self.assertIn("unique file", result.explanation.lower())

    def test_custom_scoring_weights(self):
        """Custom weights should affect the final score magnitude."""
        self._write(self.left_dir, "only_left.txt", "data\n")

        default_result = compare_directories(
            self.left_dir, self.right_dir, [],
            weights=ScoringWeights(),
        )
        heavy_result = compare_directories(
            self.left_dir, self.right_dir, [],
            weights=ScoringWeights(unique_file=10),
        )

        # Both negative (left has extra file), but heavy weight should be larger magnitude
        self.assertLess(default_result.score, 0)
        self.assertLess(heavy_result.score, 0)
        self.assertLess(heavy_result.score, default_result.score)

    def test_cancel_event(self):
        """Setting cancel_event immediately should produce an empty/cancelled result."""
        self._write(self.left_dir, "file.txt", "data\n")
        self._write(self.right_dir, "file.txt", "data\n")

        cancel = threading.Event()
        cancel.set()  # Set immediately before comparison

        result = compare_directories(
            self.left_dir, self.right_dir, [],
            cancel_event=cancel,
        )

        self.assertEqual(result.score, 0)
        self.assertEqual(len(result.rows), 0)
        self.assertIn("cancelled", result.explanation.lower())

    def test_confidence_levels(self):
        """Confidence should scale with score magnitude."""
        # Create many left-only files to push score high
        for i in range(10):
            self._write(self.left_dir, f"file{i}.txt", f"content {i}\n")

        result = compare_directories(self.left_dir, self.right_dir, [])

        self.assertIn(result.confidence, ["Low", "Medium", "High"])
        # With 10 unique files at weight 3 each = score -30, should be High confidence
        self.assertEqual(result.confidence, "High")

    def test_ignore_patterns_applied(self):
        """Files matching ignore patterns should be excluded from comparison."""
        self._write(self.left_dir, "main.py", "code\n")
        self._write(self.left_dir, "cache.pyc", "compiled\n")
        self._write(self.right_dir, "main.py", "code\n")

        result = compare_directories(
            self.left_dir, self.right_dir, ["*.pyc"],
        )

        paths = [r.rel_path for r in result.rows]
        self.assertIn("main.py", paths)
        self.assertNotIn("cache.pyc", paths)


class TestFmtSize(unittest.TestCase):
    """Tests for the fmt_size formatting function."""

    def test_bytes(self):
        """Sizes under 1 KB should display as bytes."""
        self.assertEqual(fmt_size(0), "0 B")
        self.assertEqual(fmt_size(512), "512 B")
        self.assertEqual(fmt_size(1023), "1023 B")

    def test_kilobytes(self):
        """Sizes in the KB range should display as KB."""
        result = fmt_size(1024)
        self.assertIn("KB", result)
        result = fmt_size(1536)
        self.assertIn("KB", result)
        self.assertIn("1.5", result)

    def test_megabytes(self):
        """Sizes in the MB range should display as MB."""
        result = fmt_size(1024 * 1024)
        self.assertIn("MB", result)
        result = fmt_size(5 * 1024 * 1024)
        self.assertIn("MB", result)

    def test_gigabytes(self):
        """Sizes in the GB range should display as GB."""
        result = fmt_size(1024 * 1024 * 1024)
        self.assertIn("GB", result)
        result = fmt_size(2 * 1024 * 1024 * 1024)
        self.assertIn("GB", result)

    def test_boundary_values(self):
        """Test exact boundary values between units."""
        # Exactly 1 KB
        self.assertIn("KB", fmt_size(1024))
        # Exactly 1 MB
        self.assertIn("MB", fmt_size(1024 ** 2))
        # Exactly 1 GB
        self.assertIn("GB", fmt_size(1024 ** 3))


class TestExportReportTxt(unittest.TestCase):
    """Tests for plain-text report export."""

    def setUp(self):
        """Create temp directories and run a comparison to generate a result."""
        self.left_dir = tempfile.mkdtemp()
        self.right_dir = tempfile.mkdtemp()

        filepath_left = os.path.join(self.left_dir, "file.txt")
        filepath_right = os.path.join(self.right_dir, "file.txt")
        with open(filepath_left, "w", encoding="utf-8") as f:
            f.write("hello world\n")
        with open(filepath_right, "w", encoding="utf-8") as f:
            f.write("hello world\n")

        self.result = compare_directories(self.left_dir, self.right_dir, [])

    def tearDown(self):
        """Clean up temp directories."""
        shutil.rmtree(self.left_dir, ignore_errors=True)
        shutil.rmtree(self.right_dir, ignore_errors=True)

    def test_contains_verdict(self):
        """Text report should contain the verdict."""
        report = export_report_txt(self.result)
        self.assertIn("VERDICT", report)

    def test_contains_file_paths(self):
        """Text report should contain file paths from rows."""
        report = export_report_txt(self.result)
        self.assertIn("file.txt", report)

    def test_contains_directory_paths(self):
        """Text report should contain the compared directory paths."""
        report = export_report_txt(self.result)
        # Paths are realpath'd, so check for the directory existence in the report
        self.assertIn("Left:", report)
        self.assertIn("Right:", report)

    def test_contains_header(self):
        """Text report should contain the DirCompare header."""
        report = export_report_txt(self.result)
        self.assertIn("DirCompare Report", report)


class TestExportReportCsv(unittest.TestCase):
    """Tests for CSV report export."""

    def setUp(self):
        """Create temp directories and run a comparison to generate a result."""
        self.left_dir = tempfile.mkdtemp()
        self.right_dir = tempfile.mkdtemp()

        with open(os.path.join(self.left_dir, "a.txt"), "w") as f:
            f.write("left content\n")
        with open(os.path.join(self.right_dir, "a.txt"), "w") as f:
            f.write("left content\n")
        with open(os.path.join(self.left_dir, "b.txt"), "w") as f:
            f.write("only left\n")

        self.result = compare_directories(self.left_dir, self.right_dir, [])

    def tearDown(self):
        """Clean up temp directories."""
        shutil.rmtree(self.left_dir, ignore_errors=True)
        shutil.rmtree(self.right_dir, ignore_errors=True)

    def test_csv_parseable(self):
        """CSV report should be parseable with csv.reader."""
        csv_text = export_report_csv(self.result)
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        # Header + data rows
        self.assertGreaterEqual(len(rows), 2)

    def test_csv_header(self):
        """CSV report should have the correct header (after timestamp row)."""
        csv_text = export_report_csv(self.result)
        reader = csv.reader(io.StringIO(csv_text))
        timestamp_row = next(reader)  # First row is timestamp metadata
        self.assertEqual(timestamp_row[0], "# Generated")
        header = next(reader)
        self.assertEqual(header, ["Relative Path", "Status", "Size Left", "Size Right", "Notes"])

    def test_csv_row_count(self):
        """CSV should have one row per compared file plus header and timestamp row."""
        csv_text = export_report_csv(self.result)
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        # Timestamp row + Header + number of comparison rows
        self.assertEqual(len(rows), 2 + len(self.result.rows))


class TestExportReportJson(unittest.TestCase):
    """Tests for JSON report export."""

    def setUp(self):
        """Create temp directories and run a comparison to generate a result."""
        self.left_dir = tempfile.mkdtemp()
        self.right_dir = tempfile.mkdtemp()

        with open(os.path.join(self.left_dir, "code.py"), "w") as f:
            f.write("print('hello')\n")
        with open(os.path.join(self.right_dir, "code.py"), "w") as f:
            f.write("print('hello')\nprint('world')\n")

        self.result = compare_directories(self.left_dir, self.right_dir, [])

    def tearDown(self):
        """Clean up temp directories."""
        shutil.rmtree(self.left_dir, ignore_errors=True)
        shutil.rmtree(self.right_dir, ignore_errors=True)

    def test_json_parseable(self):
        """JSON report should be parseable with json.loads."""
        json_text = export_report_json(self.result)
        data = json.loads(json_text)
        self.assertIsInstance(data, dict)

    def test_json_structure(self):
        """JSON report should have all expected top-level keys."""
        json_text = export_report_json(self.result)
        data = json.loads(json_text)
        expected_keys = {
            "left_dir", "right_dir", "left_file_count", "right_file_count",
            "left_total_size", "right_total_size", "left_versions", "right_versions",
            "score", "confidence", "verdict", "explanation", "warnings",
            "weights", "left_git_commits", "right_git_commits",
            "status_counts", "files",
        }
        self.assertTrue(expected_keys.issubset(set(data.keys())))

    def test_json_files_array(self):
        """JSON files array should have the correct structure."""
        json_text = export_report_json(self.result)
        data = json.loads(json_text)
        self.assertIsInstance(data["files"], list)
        self.assertGreater(len(data["files"]), 0)
        file_entry = data["files"][0]
        self.assertIn("path", file_entry)
        self.assertIn("status", file_entry)
        self.assertIn("size_left", file_entry)
        self.assertIn("size_right", file_entry)
        self.assertIn("notes", file_entry)

    def test_json_weights(self):
        """JSON weights object should reflect the scoring weights used."""
        json_text = export_report_json(self.result)
        data = json.loads(json_text)
        weights = data["weights"]
        self.assertIn("unique_file", weights)
        self.assertIn("content_analysis", weights)
        self.assertIn("version_string", weights)
        self.assertIn("git_commits", weights)


class TestScoringWeights(unittest.TestCase):
    """Tests for ScoringWeights defaults and custom values."""

    def test_defaults(self):
        """Default weights should have the documented default values."""
        w = ScoringWeights()
        self.assertEqual(w.unique_file, 3)
        self.assertEqual(w.content_analysis, 1)
        self.assertEqual(w.version_string, 2)
        self.assertEqual(w.git_commits, 2)

    def test_custom_values(self):
        """Custom weights should be stored correctly."""
        w = ScoringWeights(unique_file=10, content_analysis=5, version_string=8, git_commits=1)
        self.assertEqual(w.unique_file, 10)
        self.assertEqual(w.content_analysis, 5)
        self.assertEqual(w.version_string, 8)
        self.assertEqual(w.git_commits, 1)

    def test_custom_weights_affect_score(self):
        """Custom weights should change the score compared to defaults."""
        left_dir = tempfile.mkdtemp()
        right_dir = tempfile.mkdtemp()
        try:
            # Create a left-only file so unique_file weight matters
            filepath = os.path.join(left_dir, "unique.txt")
            with open(filepath, "w") as f:
                f.write("content\n")

            result_default = compare_directories(
                left_dir, right_dir, [],
                weights=ScoringWeights(),
            )
            result_heavy = compare_directories(
                left_dir, right_dir, [],
                weights=ScoringWeights(unique_file=20),
            )

            # Both should be negative, but heavy weight should be more negative
            self.assertLess(result_default.score, 0)
            self.assertLess(result_heavy.score, result_default.score)
        finally:
            shutil.rmtree(left_dir, ignore_errors=True)
            shutil.rmtree(right_dir, ignore_errors=True)


class TestProgressThrottle(unittest.TestCase):
    """Tests for the ProgressThrottle class."""

    def test_throttles_rapid_calls(self):
        """ProgressThrottle should fire fewer callbacks than total updates."""
        call_count = 0

        def callback(fraction, message=""):
            nonlocal call_count
            call_count += 1

        throttle = ProgressThrottle(callback, interval=0.1)

        # Fire many rapid updates (should be throttled)
        for i in range(100):
            throttle.update(i / 100)

        # The final call at fraction=1.0 always fires
        throttle.update(1.0)

        # Throttle should have reduced the number of calls significantly
        # At minimum: first call + final call = 2, but likely a few more
        self.assertGreater(call_count, 0)
        self.assertLess(call_count, 100)

    def test_final_update_always_fires(self):
        """Update with fraction >= 1.0 should always fire the callback."""
        fired = []

        def callback(fraction, message=""):
            fired.append(fraction)

        throttle = ProgressThrottle(callback, interval=10.0)  # Very high interval
        throttle.update(0.5)   # This fires because it's the first call (last_time=0)
        throttle.update(0.6)   # This should be throttled
        throttle.update(1.0)   # This should always fire (fraction >= 1.0)

        # The 1.0 update should have fired regardless of throttle
        self.assertIn(1.0, fired)

    def test_first_update_fires(self):
        """The very first update should always fire (since _last_time starts at 0)."""
        fired = []

        def callback(fraction, message=""):
            fired.append(fraction)

        throttle = ProgressThrottle(callback, interval=10.0)
        throttle.update(0.01)

        self.assertEqual(len(fired), 1)
        self.assertAlmostEqual(fired[0], 0.01)


class TestExportReportHtml(unittest.TestCase):
    """Tests for HTML report export."""

    def setUp(self):
        """Create temp directories and run a comparison to generate a result."""
        self.left_dir = tempfile.mkdtemp()
        self.right_dir = tempfile.mkdtemp()

        with open(os.path.join(self.left_dir, "app.py"), "w") as f:
            f.write("print('hello')\n")
        with open(os.path.join(self.right_dir, "app.py"), "w") as f:
            f.write("print('hello')\n")
        with open(os.path.join(self.left_dir, "extra.txt"), "w") as f:
            f.write("only left\n")

        self.result = compare_directories(self.left_dir, self.right_dir, [])

    def tearDown(self):
        """Clean up temp directories."""
        shutil.rmtree(self.left_dir, ignore_errors=True)
        shutil.rmtree(self.right_dir, ignore_errors=True)

    def test_contains_doctype_and_closing_tag(self):
        """HTML report should contain <!DOCTYPE html> and </html>."""
        report = export_report_html(self.result)
        self.assertIn("<!DOCTYPE html>", report)
        self.assertIn("</html>", report)

    def test_contains_verdict(self):
        """HTML report should contain the verdict text."""
        report = export_report_html(self.result)
        # Left has an extra file, so LEFT is more up to date
        self.assertIn("LEFT is more up to date", report)

    def test_contains_file_paths(self):
        """HTML report should contain file paths from rows."""
        report = export_report_html(self.result)
        self.assertIn("app.py", report)
        self.assertIn("extra.txt", report)

    def test_contains_colour_coded_rows(self):
        """HTML report should contain colour-coded rows with status values."""
        report = export_report_html(self.result)
        # Check that status values appear in the output
        self.assertIn("Identical", report)
        self.assertIn("Left Only", report)

    def test_contains_title(self):
        """HTML report should contain the DirCompare Report title."""
        report = export_report_html(self.result)
        self.assertIn("DirCompare Report", report)


class TestTimestampField(unittest.TestCase):
    """Tests for the ComparisonResult.timestamp field."""

    def setUp(self):
        """Create temp directories and run a comparison."""
        self.left_dir = tempfile.mkdtemp()
        self.right_dir = tempfile.mkdtemp()

        with open(os.path.join(self.left_dir, "file.txt"), "w") as f:
            f.write("content\n")
        with open(os.path.join(self.right_dir, "file.txt"), "w") as f:
            f.write("content\n")

        self.result = compare_directories(self.left_dir, self.right_dir, [])

    def tearDown(self):
        """Clean up temp directories."""
        shutil.rmtree(self.left_dir, ignore_errors=True)
        shutil.rmtree(self.right_dir, ignore_errors=True)

    def test_timestamp_is_non_empty(self):
        """Timestamp should be populated with a non-empty string after comparison."""
        self.assertIsInstance(self.result.timestamp, str)
        self.assertTrue(len(self.result.timestamp) > 0)

    def test_timestamp_format(self):
        """Timestamp should match the format 'YYYY-MM-DD HH:MM:SS'."""
        pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
        self.assertRegex(self.result.timestamp, pattern)


class TestFileTypeCounts(unittest.TestCase):
    """Tests for the ComparisonResult.file_type_counts field."""

    def setUp(self):
        """Create temp directories with files of known extensions."""
        self.left_dir = tempfile.mkdtemp()
        self.right_dir = tempfile.mkdtemp()

        # Create files with various extensions in both directories
        for name in ["a.py", "b.py", "c.py"]:
            with open(os.path.join(self.left_dir, name), "w") as f:
                f.write("code\n")
        for name in ["d.txt", "e.txt"]:
            with open(os.path.join(self.left_dir, name), "w") as f:
                f.write("text\n")
        with open(os.path.join(self.left_dir, "readme"), "w") as f:
            f.write("no extension\n")

        # Right directory has one .py file and one .txt file
        with open(os.path.join(self.right_dir, "a.py"), "w") as f:
            f.write("code\n")
        with open(os.path.join(self.right_dir, "d.txt"), "w") as f:
            f.write("text\n")

        self.result = compare_directories(self.left_dir, self.right_dir, [])

    def tearDown(self):
        """Clean up temp directories."""
        shutil.rmtree(self.left_dir, ignore_errors=True)
        shutil.rmtree(self.right_dir, ignore_errors=True)

    def test_file_type_counts_populated(self):
        """file_type_counts should be a non-empty dict after comparison."""
        self.assertIsInstance(self.result.file_type_counts, dict)
        self.assertGreater(len(self.result.file_type_counts), 0)

    def test_counts_correct_for_known_extensions(self):
        """file_type_counts should correctly count file extensions."""
        # All unique paths: a.py, b.py, c.py, d.txt, e.txt, readme
        # .py appears 3 times (a.py, b.py, c.py — union of both dirs)
        self.assertEqual(self.result.file_type_counts.get(".py"), 3)
        self.assertEqual(self.result.file_type_counts.get(".txt"), 2)

    def test_no_extension_counted(self):
        """Files without an extension should be counted under '(no ext)'."""
        self.assertEqual(self.result.file_type_counts.get("(no ext)"), 1)


class TestPatternCache(unittest.TestCase):
    """Tests for the _pattern_cache dictionary used by _match_pattern."""

    def test_cache_populated_on_wildcard(self):
        """_pattern_cache should be populated when wildcard patterns are used."""
        # Use a unique pattern unlikely to have been cached before
        unique_pattern = "*.test_cache_unique_ext_xyz"
        _match_pattern("file.test_cache_unique_ext_xyz", unique_pattern)
        self.assertIn(unique_pattern, _pattern_cache)

    def test_cached_pattern_returns_same_result(self):
        """Cached patterns should return the same match results as uncached ones."""
        pattern = "*.cache_reuse_test_abc"
        # First call populates the cache
        result1 = _match_pattern("file.cache_reuse_test_abc", pattern)
        self.assertIn(pattern, _pattern_cache)
        # Second call uses the cache
        result2 = _match_pattern("file.cache_reuse_test_abc", pattern)
        self.assertEqual(result1, result2)
        self.assertTrue(result1)

    def test_cached_pattern_is_compiled_regex(self):
        """Cached entries should be compiled regex Pattern objects."""
        pattern = "*.cache_type_check_qrs"
        _match_pattern("anything.cache_type_check_qrs", pattern)
        self.assertIsInstance(_pattern_cache[pattern], re_mod.Pattern)


class TestIgnoreCategoriesAndFlattenCategories(unittest.TestCase):
    """Tests for IGNORE_CATEGORIES and _flatten_categories."""

    def test_ignore_categories_is_non_empty_dict(self):
        """IGNORE_CATEGORIES should be a non-empty dict."""
        self.assertIsInstance(IGNORE_CATEGORIES, dict)
        self.assertGreater(len(IGNORE_CATEGORIES), 0)

    def test_default_ignore_patterns_derived_from_categories(self):
        """All patterns from IGNORE_CATEGORIES should appear in DEFAULT_IGNORE_PATTERNS."""
        for category, patterns_str in IGNORE_CATEGORIES.items():
            for p in patterns_str.split(","):
                p = p.strip()
                if p:
                    self.assertIn(
                        p, DEFAULT_IGNORE_PATTERNS,
                        f"Pattern '{p}' from category '{category}' not found in DEFAULT_IGNORE_PATTERNS",
                    )

    def test_flatten_categories_deduplicates(self):
        """_flatten_categories should deduplicate patterns across categories."""
        categories = {
            "Cat1": "*.pyc, __pycache__, .git",
            "Cat2": ".git, *.log, __pycache__",
        }
        result = _flatten_categories(categories)
        # Each pattern should appear only once
        self.assertEqual(len(result), len(set(result)))
        # All unique patterns should be present
        self.assertEqual(set(result), {"*.pyc", "__pycache__", ".git", "*.log"})


class TestProgressThrottleMessage(unittest.TestCase):
    """Tests for ProgressThrottle passing the message parameter to callbacks."""

    def test_message_passed_to_callback(self):
        """ProgressThrottle should pass the message parameter to callbacks."""
        received_messages = []

        def callback(fraction, message=""):
            received_messages.append(message)

        throttle = ProgressThrottle(callback, interval=0.0)
        throttle.update(0.5, "Scanning files")

        self.assertIn("Scanning files", received_messages)

    def test_final_update_passes_message(self):
        """Final update (fraction >= 1.0) should also pass the message."""
        received_messages = []

        def callback(fraction, message=""):
            received_messages.append(message)

        throttle = ProgressThrottle(callback, interval=10.0)
        throttle.update(0.01, "Starting")  # First call fires
        throttle.update(1.0, "Done")       # Final call always fires

        self.assertIn("Done", received_messages)

    def test_empty_message_default(self):
        """Callback should receive empty string when no message is provided."""
        received_messages = []

        def callback(fraction, message=""):
            received_messages.append(message)

        throttle = ProgressThrottle(callback, interval=0.0)
        throttle.update(0.5)

        self.assertIn("", received_messages)


class TestHashAlgorithm(unittest.TestCase):
    """Tests for configurable hash algorithm support."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.tmpdir, "test.txt")
        with open(self.test_file, "w") as f:
            f.write("hello world\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_default_is_md5(self):
        """scan_file without hash_algorithm should use MD5 (32-char hex)."""
        info = scan_file(self.test_file, "test.txt")
        self.assertEqual(info.hash_algorithm, "md5")
        self.assertEqual(len(info.content_hash), 32)

    def test_explicit_md5(self):
        """Explicit md5 should produce same result as default."""
        info_default = scan_file(self.test_file, "test.txt")
        info_md5 = scan_file(self.test_file, "test.txt", hash_algorithm="md5")
        self.assertEqual(info_default.content_hash, info_md5.content_hash)

    def test_sha256_produces_64_char_hash(self):
        """SHA-256 should produce a 64-character hex digest."""
        info = scan_file(self.test_file, "test.txt", hash_algorithm="sha256")
        self.assertEqual(info.hash_algorithm, "sha256")
        self.assertEqual(len(info.content_hash), 64)

    def test_sha256_differs_from_md5(self):
        """SHA-256 and MD5 hashes for the same file should differ."""
        info_md5 = scan_file(self.test_file, "test.txt", hash_algorithm="md5")
        info_sha = scan_file(self.test_file, "test.txt", hash_algorithm="sha256")
        self.assertNotEqual(info_md5.content_hash, info_sha.content_hash)

    def test_scan_directory_with_sha256(self):
        """scan_directory should pass hash_algorithm through to scan_file."""
        inv = scan_directory(self.tmpdir, [], hash_algorithm="sha256")
        self.assertEqual(len(inv), 1)
        info = list(inv.values())[0]
        self.assertEqual(info.hash_algorithm, "sha256")
        self.assertEqual(len(info.content_hash), 64)

    def test_compare_directories_with_sha256(self):
        """compare_directories should work end-to-end with SHA-256."""
        other = tempfile.mkdtemp()
        try:
            with open(os.path.join(other, "test.txt"), "w") as f:
                f.write("hello world\n")
            result = compare_directories(self.tmpdir, other, [], hash_algorithm="sha256")
            # Identical files should produce score 0
            self.assertEqual(result.score, 0)
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_invalid_algorithm_raises(self):
        """An invalid hash algorithm should raise ValueError."""
        with self.assertRaises(ValueError):
            scan_file(self.test_file, "test.txt", hash_algorithm="invalid")

    def test_empty_file_sha256(self):
        """SHA-256 of an empty file should be the known empty digest."""
        empty = os.path.join(self.tmpdir, "empty.txt")
        with open(empty, "w") as f:
            pass
        info = scan_file(empty, "empty.txt", hash_algorithm="sha256")
        # SHA-256 of empty input
        self.assertEqual(info.content_hash, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


class TestMerkleHash(unittest.TestCase):
    """Tests for directory-level Merkle hashing."""

    def setUp(self):
        self.left_dir = tempfile.mkdtemp()
        self.right_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.left_dir, ignore_errors=True)
        shutil.rmtree(self.right_dir, ignore_errors=True)

    def _write(self, base_dir, rel_path, content):
        full = os.path.join(base_dir, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    def test_empty_inventory(self):
        """compute_merkle_hash of empty dict returns empty string."""
        self.assertEqual(compute_merkle_hash({}), "")

    def test_single_file_valid_hex(self):
        """Merkle hash of single-file inventory is valid 32-char hex (md5)."""
        self._write(self.left_dir, "a.txt", "hello")
        inv = scan_directory(self.left_dir, [])
        h = compute_merkle_hash(inv, "md5")
        self.assertEqual(len(h), 32)
        # Must be valid hex
        int(h, 16)

    def test_identical_directories_match(self):
        """Identical directories produce the same Merkle hash."""
        self._write(self.left_dir, "a.txt", "hello")
        self._write(self.left_dir, "sub/b.txt", "world")
        self._write(self.right_dir, "a.txt", "hello")
        self._write(self.right_dir, "sub/b.txt", "world")
        left_inv = scan_directory(self.left_dir, [])
        right_inv = scan_directory(self.right_dir, [])
        self.assertEqual(
            compute_merkle_hash(left_inv),
            compute_merkle_hash(right_inv),
        )

    def test_different_content_differs(self):
        """Different file content produces different Merkle hashes."""
        self._write(self.left_dir, "a.txt", "hello")
        self._write(self.right_dir, "a.txt", "goodbye")
        left_inv = scan_directory(self.left_dir, [])
        right_inv = scan_directory(self.right_dir, [])
        self.assertNotEqual(
            compute_merkle_hash(left_inv),
            compute_merkle_hash(right_inv),
        )

    def test_different_file_set_differs(self):
        """Different file sets produce different Merkle hashes."""
        self._write(self.left_dir, "a.txt", "hello")
        self._write(self.right_dir, "a.txt", "hello")
        self._write(self.right_dir, "b.txt", "extra")
        left_inv = scan_directory(self.left_dir, [])
        right_inv = scan_directory(self.right_dir, [])
        self.assertNotEqual(
            compute_merkle_hash(left_inv),
            compute_merkle_hash(right_inv),
        )

    def test_deterministic_ordering(self):
        """Merkle hash is deterministic regardless of dict insertion order."""
        self._write(self.left_dir, "z.txt", "last")
        self._write(self.left_dir, "a.txt", "first")
        inv = scan_directory(self.left_dir, [])
        h1 = compute_merkle_hash(inv)
        h2 = compute_merkle_hash(inv)
        self.assertEqual(h1, h2)

    def test_respects_hash_algorithm(self):
        """Different hash algorithms produce different Merkle hashes."""
        self._write(self.left_dir, "a.txt", "hello")
        inv_md5 = scan_directory(self.left_dir, [], hash_algorithm="md5")
        inv_sha = scan_directory(self.left_dir, [], hash_algorithm="sha256")
        h_md5 = compute_merkle_hash(inv_md5, "md5")
        h_sha = compute_merkle_hash(inv_sha, "sha256")
        self.assertNotEqual(h_md5, h_sha)

    def test_fast_path_identical_dirs(self):
        """compare_directories uses Merkle fast path for identical dirs."""
        self._write(self.left_dir, "a.txt", "hello")
        self._write(self.right_dir, "a.txt", "hello")
        result = compare_directories(self.left_dir, self.right_dir, [])
        self.assertEqual(result.score, 0)
        self.assertEqual(result.left_merkle_hash, result.right_merkle_hash)
        self.assertNotEqual(result.left_merkle_hash, "")
        self.assertIn("Merkle", result.explanation)
        self.assertTrue(all(r.status == FileStatus.IDENTICAL for r in result.rows))

    def test_normal_path_populates_merkle(self):
        """compare_directories populates Merkle hashes even when dirs differ."""
        self._write(self.left_dir, "a.txt", "hello")
        self._write(self.right_dir, "a.txt", "goodbye")
        result = compare_directories(self.left_dir, self.right_dir, [])
        self.assertNotEqual(result.left_merkle_hash, "")
        self.assertNotEqual(result.right_merkle_hash, "")
        self.assertNotEqual(result.left_merkle_hash, result.right_merkle_hash)

    def test_merkle_in_json_export(self):
        """JSON export includes Merkle hash fields."""
        self._write(self.left_dir, "a.txt", "hello")
        self._write(self.right_dir, "a.txt", "hello")
        result = compare_directories(self.left_dir, self.right_dir, [])
        data = json.loads(export_report_json(result))
        self.assertIn("left_merkle_hash", data)
        self.assertIn("right_merkle_hash", data)
        self.assertIn("directories_identical", data)
        self.assertTrue(data["directories_identical"])

    def test_merkle_in_txt_export_identical(self):
        """Text export mentions Merkle hash match for identical dirs."""
        self._write(self.left_dir, "a.txt", "hello")
        self._write(self.right_dir, "a.txt", "hello")
        result = compare_directories(self.left_dir, self.right_dir, [])
        txt = export_report_txt(result)
        self.assertIn("Merkle hash match", txt)


if __name__ == "__main__":
    unittest.main()
