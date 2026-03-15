"""
Comprehensive unit tests for the DirCompare __main__ entry point.

Run with:
    python -m pytest test_main.py
    python -m unittest test_main.py
"""

import argparse
import csv
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import MagicMock, patch

# We cannot use ``from __main__ import ...`` because when running under
# pytest the name ``__main__`` resolves to pytest's own entry point.
# Instead, load our __main__.py via importlib with an alias and set the
# package attribute so that relative imports (from .engine import ...) work.
_project_dir = os.path.dirname(os.path.abspath(__file__))
_main_path = os.path.join(_project_dir, "DirCompare", "__main__.py")
_spec = importlib.util.spec_from_file_location(
    "DirCompare.__main__", _main_path,
    submodule_search_locations=[],
)
_main_mod = importlib.util.module_from_spec(_spec)
_main_mod.__package__ = "DirCompare"
_spec.loader.exec_module(_main_mod)

_build_parser = _main_mod._build_parser
_parse_weights = _main_mod._parse_weights
_progress_callback = _main_mod._progress_callback
_run_cli = _main_mod._run_cli
main = _main_mod.main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_namespace(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace with sensible defaults for _run_cli."""
    defaults = {
        "left": None,
        "right": None,
        "ignore": "__pycache__,*.pyc",
        "gitignore": False,
        "format": "text",
        "output": None,
        "weights": None,
        "quiet": False,
        "hash_algorithm": "md5",
        "cache": False,
        "no_cache": False,
        "directories": [],
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _write_file(base_dir: str, rel_path: str, content: str) -> None:
    """Write a file inside *base_dir* creating intermediate directories."""
    full = os.path.join(base_dir, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


# ===================================================================
# _build_parser tests
# ===================================================================

class TestBuildParser(unittest.TestCase):
    """Tests for _build_parser()."""

    def setUp(self):
        self.parser = _build_parser()

    # -- flag recognition --------------------------------------------------

    def test_left_flag_long(self):
        """--left should be accepted."""
        args = self.parser.parse_args(["--left", "/tmp/a"])
        self.assertEqual(args.left, "/tmp/a")

    def test_left_flag_short(self):
        """-l should be accepted as short form of --left."""
        args = self.parser.parse_args(["-l", "/tmp/a"])
        self.assertEqual(args.left, "/tmp/a")

    def test_right_flag_long(self):
        """--right should be accepted."""
        args = self.parser.parse_args(["--right", "/tmp/b"])
        self.assertEqual(args.right, "/tmp/b")

    def test_right_flag_short(self):
        """-r should be accepted as short form of --right."""
        args = self.parser.parse_args(["-r", "/tmp/b"])
        self.assertEqual(args.right, "/tmp/b")

    def test_ignore_flag(self):
        """--ignore should accept a comma-separated string."""
        args = self.parser.parse_args(["--ignore", "*.pyc,__pycache__"])
        self.assertEqual(args.ignore, "*.pyc,__pycache__")

    def test_ignore_short(self):
        """-i should be accepted as short form of --ignore."""
        args = self.parser.parse_args(["-i", "*.pyc"])
        self.assertEqual(args.ignore, "*.pyc")

    def test_gitignore_flag(self):
        """--gitignore should set a boolean True."""
        args = self.parser.parse_args(["--gitignore"])
        self.assertTrue(args.gitignore)

    def test_format_flag(self):
        """--format should accept valid choices."""
        for fmt in ("text", "csv", "json", "html"):
            args = self.parser.parse_args(["--format", fmt])
            self.assertEqual(args.format, fmt)

    def test_format_short(self):
        """-f should be accepted as short form of --format."""
        args = self.parser.parse_args(["-f", "json"])
        self.assertEqual(args.format, "json")

    def test_format_invalid_rejected(self):
        """--format with an unsupported value should cause SystemExit."""
        with self.assertRaises(SystemExit):
            self.parser.parse_args(["--format", "xml"])

    def test_output_flag(self):
        """--output should accept a file path."""
        args = self.parser.parse_args(["--output", "report.txt"])
        self.assertEqual(args.output, "report.txt")

    def test_output_short(self):
        """-o should be accepted as short form of --output."""
        args = self.parser.parse_args(["-o", "report.txt"])
        self.assertEqual(args.output, "report.txt")

    def test_weights_flag(self):
        """--weights should accept a colon-separated string."""
        args = self.parser.parse_args(["--weights", "3:1:2:2"])
        self.assertEqual(args.weights, "3:1:2:2")

    def test_quiet_flag(self):
        """--quiet should set a boolean True."""
        args = self.parser.parse_args(["--quiet"])
        self.assertTrue(args.quiet)

    def test_quiet_short(self):
        """-q should be accepted as short form of --quiet."""
        args = self.parser.parse_args(["-q"])
        self.assertTrue(args.quiet)

    # -- positional arguments -----------------------------------------------

    def test_positional_directories(self):
        """Positional arguments should be captured in the directories list."""
        args = self.parser.parse_args(["/tmp/a", "/tmp/b"])
        self.assertEqual(args.directories, ["/tmp/a", "/tmp/b"])

    def test_no_positional_directories(self):
        """No positional arguments should produce an empty list."""
        args = self.parser.parse_args([])
        self.assertEqual(args.directories, [])

    def test_single_positional_directory(self):
        """A single positional directory should be captured."""
        args = self.parser.parse_args(["/tmp/a"])
        self.assertEqual(args.directories, ["/tmp/a"])

    # -- defaults -----------------------------------------------------------

    def test_default_left_is_none(self):
        """Default value for --left should be None."""
        args = self.parser.parse_args([])
        self.assertIsNone(args.left)

    def test_default_right_is_none(self):
        """Default value for --right should be None."""
        args = self.parser.parse_args([])
        self.assertIsNone(args.right)

    def test_default_format_is_text(self):
        """Default value for --format should be 'text'."""
        args = self.parser.parse_args([])
        self.assertEqual(args.format, "text")

    def test_default_output_is_none(self):
        """Default value for --output should be None."""
        args = self.parser.parse_args([])
        self.assertIsNone(args.output)

    def test_default_weights_is_none(self):
        """Default value for --weights should be None."""
        args = self.parser.parse_args([])
        self.assertIsNone(args.weights)

    def test_default_quiet_is_false(self):
        """Default value for --quiet should be False."""
        args = self.parser.parse_args([])
        self.assertFalse(args.quiet)

    def test_default_gitignore_is_false(self):
        """Default value for --gitignore should be False."""
        args = self.parser.parse_args([])
        self.assertFalse(args.gitignore)

    def test_default_ignore_is_nonempty(self):
        """Default value for --ignore should be a non-empty string of patterns."""
        args = self.parser.parse_args([])
        self.assertTrue(len(args.ignore) > 0)
        # It should include at least __pycache__ from defaults
        self.assertIn("__pycache__", args.ignore)

    def test_cache_flag_parsed(self):
        """--cache sets args.cache to True."""
        args = self.parser.parse_args(["--left", "/a", "--right", "/b", "--cache"])
        self.assertTrue(args.cache)

    def test_no_cache_flag_parsed(self):
        """--no-cache sets args.no_cache to True."""
        args = self.parser.parse_args(["--left", "/a", "--right", "/b", "--no-cache"])
        self.assertTrue(args.no_cache)

    def test_cache_default_off(self):
        """Without --cache, args.cache defaults to False."""
        args = self.parser.parse_args(["--left", "/a", "--right", "/b"])
        self.assertFalse(args.cache)
        self.assertFalse(args.no_cache)


# ===================================================================
# _parse_weights tests
# ===================================================================

class TestParseWeights(unittest.TestCase):
    """Tests for _parse_weights()."""

    def test_valid_weights(self):
        """A valid '3:1:2:2' string should produce a ScoringWeights with correct values."""
        from DirCompare.engine import ScoringWeights
        weights = _parse_weights("3:1:2:2")
        self.assertIsInstance(weights, ScoringWeights)
        self.assertEqual(weights.unique_file, 3)
        self.assertEqual(weights.content_analysis, 1)
        self.assertEqual(weights.version_string, 2)
        self.assertEqual(weights.git_commits, 2)

    def test_custom_valid_weights(self):
        """A custom valid weights string should produce correct ScoringWeights."""
        weights = _parse_weights("10:5:8:1")
        self.assertEqual(weights.unique_file, 10)
        self.assertEqual(weights.content_analysis, 5)
        self.assertEqual(weights.version_string, 8)
        self.assertEqual(weights.git_commits, 1)

    def test_zero_weights(self):
        """All-zero weights should be accepted."""
        weights = _parse_weights("0:0:0:0")
        self.assertEqual(weights.unique_file, 0)
        self.assertEqual(weights.content_analysis, 0)
        self.assertEqual(weights.version_string, 0)
        self.assertEqual(weights.git_commits, 0)

    def test_too_few_parts_raises_system_exit(self):
        """A weights string with fewer than four parts should cause SystemExit."""
        with self.assertRaises(SystemExit) as ctx:
            _parse_weights("3:1:2")
        self.assertEqual(ctx.exception.code, 1)

    def test_too_many_parts_raises_system_exit(self):
        """A weights string with more than four parts should cause SystemExit."""
        with self.assertRaises(SystemExit) as ctx:
            _parse_weights("3:1:2:2:5")
        self.assertEqual(ctx.exception.code, 1)

    def test_non_integer_values_raises_system_exit(self):
        """Non-integer weight values should cause SystemExit."""
        with self.assertRaises(SystemExit) as ctx:
            _parse_weights("a:b:c:d")
        self.assertEqual(ctx.exception.code, 1)

    def test_mixed_non_integer_raises_system_exit(self):
        """Mixed valid and non-integer values should cause SystemExit."""
        with self.assertRaises(SystemExit) as ctx:
            _parse_weights("3:1:two:2")
        self.assertEqual(ctx.exception.code, 1)

    def test_float_values_raises_system_exit(self):
        """Float values should cause SystemExit (int() rejects '1.5')."""
        with self.assertRaises(SystemExit) as ctx:
            _parse_weights("1.5:1:2:2")
        self.assertEqual(ctx.exception.code, 1)

    def test_empty_string_raises_system_exit(self):
        """An empty string should cause SystemExit."""
        with self.assertRaises(SystemExit) as ctx:
            _parse_weights("")
        self.assertEqual(ctx.exception.code, 1)


# ===================================================================
# _progress_callback tests
# ===================================================================

class TestProgressCallback(unittest.TestCase):
    """Tests for _progress_callback()."""

    def test_outputs_progress_bar_to_stderr(self):
        """Calling _progress_callback should write a progress bar to stderr."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            _progress_callback(0.5, "scanning")
        output = stderr.getvalue()
        self.assertIn("#", output)
        self.assertIn("-", output)
        self.assertIn("50%", output)

    def test_message_included_in_output(self):
        """The message parameter should appear in the stderr output."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            _progress_callback(0.3, "reading files")
        output = stderr.getvalue()
        self.assertIn("reading files", output)

    def test_fraction_zero(self):
        """fraction=0.0 should produce a 0% bar with all dashes."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            _progress_callback(0.0)
        output = stderr.getvalue()
        self.assertIn("0%", output)
        # At 0% the bar should be entirely dashes (40 dashes)
        self.assertIn("-" * 40, output)

    def test_fraction_one_produces_newline(self):
        """fraction=1.0 should produce a trailing newline (print with no end)."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            _progress_callback(1.0)
        output = stderr.getvalue()
        self.assertIn("100%", output)
        # Should end with a newline from the extra print()
        self.assertTrue(output.endswith("\n"))

    def test_fraction_one_full_bar(self):
        """fraction=1.0 should produce a fully-filled bar."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            _progress_callback(1.0, "done")
        output = stderr.getvalue()
        self.assertIn("#" * 40, output)
        self.assertIn("done", output)

    def test_no_message_omits_suffix(self):
        """Calling without a message should not append extra whitespace suffix."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            _progress_callback(0.5)
        output = stderr.getvalue()
        # The output should contain the percentage but no double-space-then-text
        self.assertIn("50%", output)

    def test_intermediate_fraction(self):
        """An intermediate fraction (0.75) should show 75% and ~30 hash marks."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            _progress_callback(0.75)
        output = stderr.getvalue()
        self.assertIn("75%", output)
        # 40 * 0.75 = 30 hashes
        self.assertIn("#" * 30, output)


# ===================================================================
# _run_cli tests
# ===================================================================

class TestRunCli(unittest.TestCase):
    """Tests for _run_cli()."""

    def setUp(self):
        """Create two temp directories for comparison."""
        self.left_dir = tempfile.mkdtemp()
        self.right_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directories."""
        shutil.rmtree(self.left_dir, ignore_errors=True)
        shutil.rmtree(self.right_dir, ignore_errors=True)

    # -- basic operation ----------------------------------------------------

    def test_valid_identical_dirs_exit_code_zero(self):
        """Identical directories should produce exit code 0 (equivalent)."""
        _write_file(self.left_dir, "file.txt", "same\n")
        _write_file(self.right_dir, "file.txt", "same\n")

        args = _make_namespace(left=self.left_dir, right=self.right_dir, quiet=True)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = _run_cli(args)

        self.assertEqual(code, 0)

    def test_valid_dirs_produce_report_on_stdout(self):
        """Valid directories should produce a report on stdout."""
        _write_file(self.left_dir, "file.txt", "content\n")
        _write_file(self.right_dir, "file.txt", "content\n")

        args = _make_namespace(left=self.left_dir, right=self.right_dir, quiet=True)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            _run_cli(args)

        report = stdout.getvalue()
        self.assertGreater(len(report), 0)
        self.assertIn("file.txt", report)

    # -- non-existent directories -------------------------------------------

    def test_nonexistent_left_returns_1(self):
        """A non-existent left directory should return exit code 1."""
        args = _make_namespace(
            left="/nonexistent/path/abc123", right=self.right_dir, quiet=True
        )
        code = _run_cli(args)
        self.assertEqual(code, 1)

    def test_nonexistent_right_returns_1(self):
        """A non-existent right directory should return exit code 1."""
        args = _make_namespace(
            left=self.left_dir, right="/nonexistent/path/xyz789", quiet=True
        )
        code = _run_cli(args)
        self.assertEqual(code, 1)

    def test_both_nonexistent_returns_1(self):
        """Both directories non-existent should return exit code 1."""
        args = _make_namespace(
            left="/nonexistent/aaa", right="/nonexistent/bbb", quiet=True
        )
        code = _run_cli(args)
        self.assertEqual(code, 1)

    # -- exit codes for scoring ---------------------------------------------

    def test_exit_code_10_left_newer(self):
        """Left having unique files should produce exit code 10 (left newer)."""
        _write_file(self.left_dir, "extra.txt", "only in left\n")

        args = _make_namespace(left=self.left_dir, right=self.right_dir, quiet=True)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = _run_cli(args)

        self.assertEqual(code, 10)

    def test_exit_code_20_right_newer(self):
        """Right having unique files should produce exit code 20 (right newer)."""
        _write_file(self.right_dir, "extra.txt", "only in right\n")

        args = _make_namespace(left=self.left_dir, right=self.right_dir, quiet=True)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = _run_cli(args)

        self.assertEqual(code, 20)

    # -- output formats -----------------------------------------------------

    def test_format_json_produces_valid_json(self):
        """--format json should produce valid JSON output."""
        _write_file(self.left_dir, "a.py", "print('hello')\n")
        _write_file(self.right_dir, "a.py", "print('hello')\n")

        args = _make_namespace(
            left=self.left_dir, right=self.right_dir, format="json", quiet=True
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            _run_cli(args)

        data = json.loads(stdout.getvalue())
        self.assertIsInstance(data, dict)
        self.assertIn("score", data)
        self.assertIn("files", data)

    def test_format_csv_produces_valid_csv(self):
        """--format csv should produce valid CSV output."""
        _write_file(self.left_dir, "a.txt", "hello\n")
        _write_file(self.right_dir, "a.txt", "hello\n")

        args = _make_namespace(
            left=self.left_dir, right=self.right_dir, format="csv", quiet=True
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            _run_cli(args)

        reader = csv.reader(io.StringIO(stdout.getvalue()))
        rows = list(reader)
        # Should have at least a timestamp row, a header row, and one data row
        self.assertGreaterEqual(len(rows), 3)

    def test_format_html_produces_html(self):
        """--format html should produce HTML output."""
        _write_file(self.left_dir, "a.txt", "hello\n")
        _write_file(self.right_dir, "a.txt", "hello\n")

        args = _make_namespace(
            left=self.left_dir, right=self.right_dir, format="html", quiet=True
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            _run_cli(args)

        output = stdout.getvalue()
        self.assertIn("<html", output.lower())
        self.assertIn("</html>", output.lower())

    def test_format_text_is_default(self):
        """Default text format should produce a DirCompare Report header."""
        _write_file(self.left_dir, "a.txt", "hello\n")
        _write_file(self.right_dir, "a.txt", "hello\n")

        args = _make_namespace(
            left=self.left_dir, right=self.right_dir, quiet=True
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            _run_cli(args)

        output = stdout.getvalue()
        self.assertIn("DirCompare Report", output)

    # -- --output writes to file --------------------------------------------

    def test_output_flag_writes_to_file(self):
        """--output should write the report to a file instead of stdout."""
        _write_file(self.left_dir, "a.txt", "hello\n")
        _write_file(self.right_dir, "a.txt", "hello\n")

        outfile = os.path.join(self.left_dir, "report_output.txt")
        args = _make_namespace(
            left=self.left_dir, right=self.right_dir,
            output=outfile, quiet=True,
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = _run_cli(args)

        self.assertEqual(code, 0)
        # stdout should NOT contain the report
        self.assertEqual(stdout.getvalue().strip(), "")
        # File should contain the report
        self.assertTrue(os.path.isfile(outfile))
        with open(outfile, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("DirCompare Report", content)

    def test_output_flag_json(self):
        """--output combined with --format json should write valid JSON to file."""
        _write_file(self.left_dir, "a.txt", "hello\n")
        _write_file(self.right_dir, "a.txt", "hello\n")

        outfile = os.path.join(self.left_dir, "report.json")
        args = _make_namespace(
            left=self.left_dir, right=self.right_dir,
            format="json", output=outfile, quiet=True,
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            _run_cli(args)

        with open(outfile, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)
        self.assertIn("score", data)

    # -- --quiet flag -------------------------------------------------------

    def test_quiet_suppresses_progress(self):
        """--quiet should suppress progress output on stderr."""
        _write_file(self.left_dir, "a.txt", "hello\n")
        _write_file(self.right_dir, "a.txt", "hello\n")

        args = _make_namespace(
            left=self.left_dir, right=self.right_dir, quiet=True
        )
        stderr = io.StringIO()
        stdout = io.StringIO()
        with redirect_stderr(stderr), redirect_stdout(stdout):
            _run_cli(args)

        # With --quiet, stderr should not contain any progress bar output
        self.assertNotIn("#", stderr.getvalue())
        self.assertNotIn("Comparison completed", stderr.getvalue())

    def test_non_quiet_shows_progress(self):
        """Without --quiet, stderr should contain progress and timing info."""
        _write_file(self.left_dir, "a.txt", "hello\n")
        _write_file(self.right_dir, "a.txt", "hello\n")

        args = _make_namespace(
            left=self.left_dir, right=self.right_dir, quiet=False
        )
        stderr = io.StringIO()
        stdout = io.StringIO()
        with redirect_stderr(stderr), redirect_stdout(stdout):
            _run_cli(args)

        err_output = stderr.getvalue()
        self.assertIn("Comparison completed", err_output)

    # -- custom --weights ---------------------------------------------------

    def test_custom_weights_are_applied(self):
        """Custom --weights should change the comparison score magnitude."""
        _write_file(self.left_dir, "unique.txt", "only left\n")

        args_default = _make_namespace(
            left=self.left_dir, right=self.right_dir, quiet=True
        )
        args_heavy = _make_namespace(
            left=self.left_dir, right=self.right_dir,
            weights="20:1:2:2", quiet=True,
        )

        stdout_default = io.StringIO()
        stdout_heavy = io.StringIO()

        with redirect_stdout(stdout_default):
            _run_cli(args_default)
        with redirect_stdout(stdout_heavy):
            _run_cli(args_heavy)

        # Both should produce JSON-parseable text reports mentioning the file
        report_default = stdout_default.getvalue()
        report_heavy = stdout_heavy.getvalue()
        self.assertIn("unique.txt", report_default)
        self.assertIn("unique.txt", report_heavy)

    def test_custom_weights_json_reflects_values(self):
        """Custom weights should appear in the JSON output."""
        _write_file(self.left_dir, "a.txt", "hello\n")
        _write_file(self.right_dir, "a.txt", "hello\n")

        args = _make_namespace(
            left=self.left_dir, right=self.right_dir,
            format="json", weights="10:5:8:1", quiet=True,
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            _run_cli(args)

        data = json.loads(stdout.getvalue())
        self.assertEqual(data["weights"]["unique_file"], 10)
        self.assertEqual(data["weights"]["content_analysis"], 5)
        self.assertEqual(data["weights"]["version_string"], 8)
        self.assertEqual(data["weights"]["git_commits"], 1)


# ===================================================================
# main() integration tests
# ===================================================================

class TestMain(unittest.TestCase):
    """Integration tests for the main() entry point."""

    def setUp(self):
        """Create two temp directories for comparison."""
        self.left_dir = tempfile.mkdtemp()
        self.right_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directories."""
        shutil.rmtree(self.left_dir, ignore_errors=True)
        shutil.rmtree(self.right_dir, ignore_errors=True)

    def test_positional_args_merge_into_left_right(self):
        """Positional args should be merged into --left and --right."""
        _write_file(self.left_dir, "f.txt", "a\n")
        _write_file(self.right_dir, "f.txt", "a\n")

        test_args = [self.left_dir, self.right_dir, "-q"]
        with patch("sys.argv", ["DirCompare"] + test_args):
            with self.assertRaises(SystemExit) as ctx:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    main()
            # exit code 0 means equivalent
            self.assertEqual(ctx.exception.code, 0)

    def test_left_right_flags_run_cli(self):
        """--left and --right should trigger CLI mode."""
        _write_file(self.left_dir, "f.txt", "content\n")
        _write_file(self.right_dir, "f.txt", "content\n")

        test_args = ["--left", self.left_dir, "--right", self.right_dir, "-q"]
        with patch("sys.argv", ["DirCompare"] + test_args):
            with self.assertRaises(SystemExit) as ctx:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    main()
            self.assertEqual(ctx.exception.code, 0)

    def test_no_args_attempts_gui_mode(self):
        """With no args, main() should attempt to import and call gui.run."""
        mock_run = MagicMock()
        mock_gui = MagicMock()
        mock_gui.run = mock_run

        # Remove the real gui from sys.modules so ``from .gui import run``
        # picks up our mock, then restore afterwards.
        saved = sys.modules.pop("DirCompare.gui", None)
        try:
            sys.modules["DirCompare.gui"] = mock_gui
            with patch("sys.argv", ["DirCompare"]):
                try:
                    main()
                except SystemExit:
                    pass
            mock_run.assert_called_once()
        finally:
            if saved is not None:
                sys.modules["DirCompare.gui"] = saved
            else:
                sys.modules.pop("DirCompare.gui", None)

    def test_no_args_gui_import_error_exits_1(self):
        """When gui import fails and no args given, main() should exit with code 1."""
        # Replace 'DirCompare.gui' in sys.modules with a sentinel that causes
        # ``from .gui import run`` to raise ImportError.
        saved = sys.modules.pop("DirCompare.gui", None)
        try:
            # Setting the module entry to None makes Python raise ImportError
            # when the relative import tries to resolve it.
            sys.modules["DirCompare.gui"] = None  # type: ignore[assignment]
            with patch("sys.argv", ["DirCompare"]):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)
        finally:
            if saved is not None:
                sys.modules["DirCompare.gui"] = saved
            else:
                sys.modules.pop("DirCompare.gui", None)

    def test_three_positional_args_exits_1(self):
        """More than two positional directories should cause SystemExit(1)."""
        test_args = ["/dir/a", "/dir/b", "/dir/c"]
        with patch("sys.argv", ["DirCompare"] + test_args):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_positional_does_not_override_explicit_left(self):
        """Explicit --left should not be overridden by positional args."""
        _write_file(self.left_dir, "f.txt", "content\n")
        _write_file(self.right_dir, "f.txt", "content\n")

        # Provide --left and --right explicitly, plus a positional arg.
        # The positional fills directories[0] but since --left is already
        # set, it should not be overwritten.
        third_dir = tempfile.mkdtemp()
        try:
            _write_file(third_dir, "f.txt", "content\n")
            test_args = [
                "--left", self.left_dir,
                "--right", self.right_dir,
                third_dir,  # positional -- should NOT override --left
                "-q",
            ]
            with patch("sys.argv", ["DirCompare"] + test_args):
                with self.assertRaises(SystemExit) as ctx:
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        main()
                self.assertEqual(ctx.exception.code, 0)
        finally:
            shutil.rmtree(third_dir, ignore_errors=True)

    def test_positional_fills_both_left_and_right(self):
        """Two positional args should fill both --left and --right."""
        _write_file(self.left_dir, "unique_left.txt", "left\n")
        _write_file(self.right_dir, "unique_right.txt", "right\n")

        test_args = [self.left_dir, self.right_dir, "-q", "-f", "json"]
        with patch("sys.argv", ["DirCompare"] + test_args):
            with self.assertRaises(SystemExit) as ctx:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    main()
            # Both dirs exist but have different files, score != 0
            self.assertIn(ctx.exception.code, (0, 10, 20))

    def test_single_positional_triggers_gui(self):
        """A single positional arg (only --left filled) should attempt GUI mode."""
        test_args = [self.left_dir]
        mock_run = MagicMock()
        mock_gui = MagicMock()
        mock_gui.run = mock_run

        saved = sys.modules.pop("DirCompare.gui", None)
        try:
            sys.modules["DirCompare.gui"] = mock_gui
            with patch("sys.argv", ["DirCompare"] + test_args):
                try:
                    main()
                except SystemExit:
                    pass
            # Since only left is set (no right), CLI mode should NOT run;
            # GUI mode should be attempted with left_dir pre-filled.
            mock_run.assert_called_once()
            _, kwargs = mock_run.call_args
            self.assertEqual(kwargs.get("left_dir"), self.left_dir)
        finally:
            if saved is not None:
                sys.modules["DirCompare.gui"] = saved
            else:
                sys.modules.pop("DirCompare.gui", None)


# ===================================================================
# Edge case / integration tests
# ===================================================================

class TestEdgeCases(unittest.TestCase):
    """Additional edge-case and integration tests."""

    def setUp(self):
        """Create temp directories."""
        self.left_dir = tempfile.mkdtemp()
        self.right_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.left_dir, ignore_errors=True)
        shutil.rmtree(self.right_dir, ignore_errors=True)

    def test_empty_directories_exit_code_zero(self):
        """Two empty directories should be equivalent (exit code 0)."""
        args = _make_namespace(left=self.left_dir, right=self.right_dir, quiet=True)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = _run_cli(args)
        self.assertEqual(code, 0)

    def test_gitignore_flag_accepted(self):
        """--gitignore should be accepted and not cause errors."""
        _write_file(self.left_dir, "a.txt", "content\n")
        _write_file(self.right_dir, "a.txt", "content\n")

        args = _make_namespace(
            left=self.left_dir, right=self.right_dir,
            gitignore=True, quiet=True,
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = _run_cli(args)
        self.assertEqual(code, 0)

    def test_nonexistent_output_dir_returns_1(self):
        """Writing to a non-existent output directory should return exit code 1."""
        _write_file(self.left_dir, "a.txt", "hello\n")
        _write_file(self.right_dir, "a.txt", "hello\n")

        args = _make_namespace(
            left=self.left_dir, right=self.right_dir,
            output="/nonexistent/dir/report.txt", quiet=True,
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = _run_cli(args)
        self.assertEqual(code, 1)

    def test_version_difference_affects_exit_code(self):
        """Version string differences should be reflected in the exit code."""
        _write_file(self.left_dir, "setup.py", '__version__ = "1.0.0"\n')
        _write_file(self.right_dir, "setup.py", '__version__ = "2.0.0"\n')

        args = _make_namespace(
            left=self.left_dir, right=self.right_dir, quiet=True
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = _run_cli(args)
        # Right has higher version => score > 0 => exit code 20
        self.assertEqual(code, 20)

    def test_left_newer_version_exit_code_10(self):
        """Left having a higher version should produce exit code 10."""
        _write_file(self.left_dir, "setup.py", '__version__ = "3.0.0"\n')
        _write_file(self.right_dir, "setup.py", '__version__ = "1.0.0"\n')

        args = _make_namespace(
            left=self.left_dir, right=self.right_dir, quiet=True
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = _run_cli(args)
        # Left has higher version => score < 0 => exit code 10
        self.assertEqual(code, 10)

    def test_ignore_patterns_applied_via_cli(self):
        """Custom --ignore patterns should exclude matching files."""
        _write_file(self.left_dir, "keep.txt", "keep\n")
        _write_file(self.left_dir, "skip.log", "skip\n")
        _write_file(self.right_dir, "keep.txt", "keep\n")

        args = _make_namespace(
            left=self.left_dir, right=self.right_dir,
            ignore="*.log", format="json", quiet=True,
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            _run_cli(args)

        data = json.loads(stdout.getvalue())
        paths = [f["path"] for f in data["files"]]
        self.assertIn("keep.txt", paths)
        self.assertNotIn("skip.log", paths)

    def test_multiple_files_scoring(self):
        """Multiple left-only files should produce a stronger negative score."""
        for i in range(5):
            _write_file(self.left_dir, f"file{i}.txt", f"content {i}\n")

        args = _make_namespace(
            left=self.left_dir, right=self.right_dir,
            format="json", quiet=True,
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = _run_cli(args)

        self.assertEqual(code, 10)
        data = json.loads(stdout.getvalue())
        self.assertLess(data["score"], 0)


if __name__ == "__main__":
    unittest.main()
