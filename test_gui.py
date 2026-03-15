"""
Comprehensive GUI tests for DirCompare.
Tests widget creation, state management, filtering, sorting, summary display,
diff viewer, ignore patterns, and various UI interactions.
"""

import os
import sys
import tempfile
import textwrap
import unittest

# ---------------------------------------------------------------------------
# Skip the entire module in headless environments where Tk cannot initialise
# ---------------------------------------------------------------------------
try:
    import tkinter as tk

    _test_root = tk.Tk()
    _test_root.withdraw()
    _test_root.destroy()
    _TK_AVAILABLE = True
except (tk.TclError, Exception):
    _TK_AVAILABLE = False

if not _TK_AVAILABLE:
    raise unittest.SkipTest("Tk display not available (headless environment)")

from tkinter import ttk

from DirCompare.engine import ComparisonResult, ComparisonRow, FileStatus, ScoringWeights, fmt_size
from DirCompare.gui import DiffViewer, DirCompareApp, IgnorePatternsDialog, SettingsDialog


def _create_tk_root():
    """Create a Tk root, skipping the test if Tcl/Tk handle exhaustion occurs."""
    try:
        root = tk.Tk()
        root.withdraw()
        return root
    except tk.TclError:
        raise unittest.SkipTest("Tk unavailable (handle exhaustion during rapid test execution)")


# ---------------------------------------------------------------------------
# Helper: build ComparisonResult objects for testing
# ---------------------------------------------------------------------------

def _make_result(
    left_dir="/tmp/left",
    right_dir="/tmp/right",
    rows=None,
    score=0,
    confidence="Low",
    explanation="No significant differences found.",
    warnings=None,
    left_file_count=0,
    right_file_count=0,
    left_total_size=0,
    right_total_size=0,
    left_versions=None,
    right_versions=None,
    weights=None,
    left_git_commits=None,
    right_git_commits=None,
    status_counts=None,
    timestamp="2026-01-15 12:00:00",
    file_type_counts=None,
):
    """Create a ComparisonResult with sensible defaults for testing."""
    if rows is None:
        rows = []
    if warnings is None:
        warnings = []
    if left_versions is None:
        left_versions = []
    if right_versions is None:
        right_versions = []
    if weights is None:
        weights = ScoringWeights()
    if status_counts is None:
        status_counts = {}
    if file_type_counts is None:
        file_type_counts = {}

    return ComparisonResult(
        left_dir=left_dir,
        right_dir=right_dir,
        left_file_count=left_file_count,
        right_file_count=right_file_count,
        left_total_size=left_total_size,
        right_total_size=right_total_size,
        left_versions=left_versions,
        right_versions=right_versions,
        score=score,
        confidence=confidence,
        explanation=explanation,
        rows=rows,
        warnings=warnings,
        weights=weights,
        left_git_commits=left_git_commits,
        right_git_commits=right_git_commits,
        status_counts=status_counts,
        timestamp=timestamp,
        file_type_counts=file_type_counts,
    )


def _make_row(
    rel_path="file.txt",
    status=FileStatus.IDENTICAL,
    size_left=100,
    size_right=100,
    notes="",
    left_path=None,
    right_path=None,
):
    """Create a ComparisonRow with sensible defaults for testing."""
    return ComparisonRow(
        rel_path=rel_path,
        status=status,
        size_left=size_left,
        size_right=size_right,
        notes=notes,
        left_path=left_path,
        right_path=right_path,
    )


# ===========================================================================
# Test: Application Creation and Widget Existence
# ===========================================================================

class TestAppCreation(unittest.TestCase):
    """Tests for creating the DirCompareApp and verifying widget existence."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_root_window_exists(self):
        """Root window should be created and have the correct title."""
        self.assertEqual(self.root.title(), "DirCompare")

    def test_root_minimum_size(self):
        """Root should have minimum size of 900x600."""
        self.root.update_idletasks()
        minwidth = self.root.minsize()[0]
        minheight = self.root.minsize()[1]
        self.assertEqual(minwidth, 900)
        self.assertEqual(minheight, 600)

    def test_directory_variables_exist(self):
        """Left and right directory StringVars should exist as StringVar instances."""
        self.assertIsInstance(self.app.left_var, tk.StringVar)
        self.assertIsInstance(self.app.right_var, tk.StringVar)
        # Values may be empty, placeholder text, or remembered from config
        self.assertIsInstance(self.app.left_var.get(), str)
        self.assertIsInstance(self.app.right_var.get(), str)

    def test_ignore_var_has_defaults(self):
        """Ignore patterns variable should have default patterns."""
        val = self.app.ignore_var.get()
        self.assertIn("__pycache__", val)
        self.assertIn("node_modules", val)
        self.assertIn(".git", val)

    def test_use_gitignore_default(self):
        """Use .gitignore checkbox should be unchecked by default."""
        self.assertFalse(self.app.use_gitignore_var.get())

    def test_treeview_exists(self):
        """Treeview widget should exist with expected columns."""
        self.assertIsInstance(self.app.tree, ttk.Treeview)
        columns = self.app.tree["columns"]
        self.assertIn("rel_path", columns)
        self.assertIn("status", columns)
        self.assertIn("size_left", columns)
        self.assertIn("size_right", columns)
        self.assertIn("notes", columns)

    def test_compare_button_exists_and_enabled(self):
        """Compare button should exist and be enabled initially."""
        self.assertIsInstance(self.app.compare_btn, ttk.Button)
        state = str(self.app.compare_btn.cget("state"))
        self.assertNotIn("disabled", state)

    def test_cancel_button_initially_disabled(self):
        """Cancel button should be disabled initially."""
        state = str(self.app.cancel_btn.cget("state"))
        self.assertIn("disabled", state)

    def test_export_button_initially_disabled(self):
        """Export button should be disabled initially."""
        state = str(self.app.export_btn.cget("state"))
        self.assertIn("disabled", state)

    def test_recompare_button_initially_disabled(self):
        """Re-compare button should be disabled before any comparison."""
        state = str(self.app.recompare_btn.cget("state"))
        self.assertIn("disabled", state)

    def test_progress_bar_exists(self):
        """Progress bar should exist and start at zero."""
        self.assertIsInstance(self.app.progress_bar, ttk.Progressbar)
        self.assertAlmostEqual(self.app.progress_var.get(), 0.0)

    def test_status_label_initial_text(self):
        """Status label should initially show 'Ready'."""
        text = self.app.status_label.cget("text")
        self.assertEqual(text, "Ready")

    def test_summary_text_widget_exists(self):
        """Summary text widget should exist and be disabled (read-only)."""
        self.assertIsInstance(self.app.summary_text, tk.Text)
        state = self.app.summary_text.cget("state")
        self.assertEqual(str(state), "disabled")

    def test_search_entry_exists(self):
        """Search entry should exist."""
        self.assertIsInstance(self.app.search_entry, ttk.Entry)

    def test_filter_checkboxes_created(self):
        """Filter checkboxes should exist for each FileStatus."""
        for status in FileStatus:
            self.assertIn(status.value, self.app._filter_vars)
            self.assertIn(status.value, self.app._filter_cbs)

    def test_all_filters_enabled_by_default(self):
        """All filter checkboxes should be checked by default."""
        for status in FileStatus:
            self.assertTrue(
                self.app._filter_vars[status.value].get(),
                f"Filter for {status.value} should be True",
            )

    def test_initial_weights(self):
        """Initial scoring weights should be defaults."""
        self.assertEqual(self.app.weights.unique_file, 3)
        self.assertEqual(self.app.weights.content_analysis, 1)
        self.assertEqual(self.app.weights.version_string, 2)
        self.assertEqual(self.app.weights.git_commits, 2)

    def test_result_initially_none(self):
        """No comparison result should exist initially."""
        self.assertIsNone(self.app.result)

    def test_all_rows_initially_empty(self):
        """The all_rows list should be empty before any comparison."""
        self.assertEqual(self.app.all_rows, [])

    def test_comparing_initially_false(self):
        """The comparing flag should be False initially."""
        self.assertFalse(self.app._comparing)

    def test_treeview_has_row_tags(self):
        """Treeview should have colour tags for each status."""
        for status_value, (tag_name, _bg) in DirCompareApp.STATUS_TAGS.items():
            # If the tag is configured, tag_configure returns a dict with 'background' key
            config = self.app.tree.tag_configure(tag_name)
            self.assertIsNotNone(config)

    def test_copy_summary_button_exists(self):
        """Copy summary button should exist."""
        self.assertIsInstance(self.app.copy_summary_btn, ttk.Button)

    def test_ignore_summary_label_exists(self):
        """Ignore summary label should show pattern count."""
        text = self.app.ignore_summary_label.cget("text")
        self.assertIn("patterns", text)

    def test_showing_label_initially_empty(self):
        """Showing label should be empty initially."""
        text = self.app.showing_label.cget("text")
        self.assertEqual(text, "")


# ===========================================================================
# Test: Swap Directories
# ===========================================================================

class TestSwapDirs(unittest.TestCase):
    """Tests for the swap directories functionality."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_swap_dirs_exchanges_values(self):
        """Swapping should exchange left and right directory paths."""
        self.app.left_var.set("/path/to/left")
        self.app.right_var.set("/path/to/right")
        self.app._swap_dirs()
        self.assertEqual(self.app.left_var.get(), "/path/to/right")
        self.assertEqual(self.app.right_var.get(), "/path/to/left")

    def test_swap_dirs_with_one_empty(self):
        """Swapping with one empty should move the value."""
        self.app.left_var.set("/some/dir")
        self.app.right_var.set("")
        self.app._swap_dirs()
        self.assertEqual(self.app.left_var.get(), "")
        self.assertEqual(self.app.right_var.get(), "/some/dir")

    def test_swap_dirs_both_empty(self):
        """Swapping both empty should be a no-op."""
        self.app.left_var.set("")
        self.app.right_var.set("")
        self.app._swap_dirs()
        self.assertEqual(self.app.left_var.get(), "")
        self.assertEqual(self.app.right_var.get(), "")

    def test_swap_dirs_double_swap_restores(self):
        """Double swap should restore original values."""
        self.app.left_var.set("AAA")
        self.app.right_var.set("BBB")
        self.app._swap_dirs()
        self.app._swap_dirs()
        self.assertEqual(self.app.left_var.get(), "AAA")
        self.assertEqual(self.app.right_var.get(), "BBB")


# ===========================================================================
# Test: on_compare_done
# ===========================================================================

class TestOnCompareDone(unittest.TestCase):
    """Tests for the _on_compare_done callback that processes comparison results."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.app._comparing = True
        self.app._compare_start_time = 0.0
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _simulate_done(self, result):
        """Simulate _on_compare_done as if a comparison just finished."""
        import time
        self.app._compare_start_time = time.monotonic() - 0.5
        self.app._on_compare_done(result)
        self.root.update_idletasks()

    def test_stores_result(self):
        """on_compare_done should store the result."""
        result = _make_result()
        self._simulate_done(result)
        self.assertIs(self.app.result, result)

    def test_comparing_flag_cleared(self):
        """on_compare_done should clear the comparing flag."""
        result = _make_result()
        self._simulate_done(result)
        self.assertFalse(self.app._comparing)

    def test_compare_button_re_enabled(self):
        """Compare button should be re-enabled after comparison."""
        result = _make_result()
        self._simulate_done(result)
        state = str(self.app.compare_btn.cget("state"))
        self.assertNotIn("disabled", state)

    def test_cancel_button_disabled(self):
        """Cancel button should be disabled after comparison."""
        result = _make_result()
        self._simulate_done(result)
        state = str(self.app.cancel_btn.cget("state"))
        self.assertIn("disabled", state)

    def test_export_button_enabled(self):
        """Export button should be enabled after comparison."""
        result = _make_result()
        self._simulate_done(result)
        state = str(self.app.export_btn.cget("state"))
        self.assertNotIn("disabled", state)

    def test_recompare_button_enabled(self):
        """Re-compare button should be enabled after comparison."""
        result = _make_result()
        self._simulate_done(result)
        state = str(self.app.recompare_btn.cget("state"))
        self.assertNotIn("disabled", state)

    def test_progress_at_100(self):
        """Progress should be at 100% after comparison."""
        result = _make_result()
        self._simulate_done(result)
        self.assertEqual(self.app.progress_var.get(), 100)

    def test_status_label_shows_time(self):
        """Status label should show elapsed time."""
        result = _make_result()
        self._simulate_done(result)
        text = self.app.status_label.cget("text")
        self.assertIn("Done in", text)
        self.assertIn("s", text)

    def test_all_rows_populated(self):
        """all_rows should be populated from the result."""
        rows = [
            _make_row(rel_path="a.txt", status=FileStatus.IDENTICAL),
            _make_row(rel_path="b.txt", status=FileStatus.LEFT_ONLY),
        ]
        result = _make_result(rows=rows)
        self._simulate_done(result)
        self.assertEqual(len(self.app.all_rows), 2)

    def test_treeview_populated(self):
        """Treeview should contain rows after comparison."""
        rows = [
            _make_row(rel_path="file1.txt", status=FileStatus.IDENTICAL),
            _make_row(rel_path="file2.txt", status=FileStatus.LEFT_ONLY),
            _make_row(rel_path="file3.txt", status=FileStatus.RIGHT_ONLY),
        ]
        result = _make_result(rows=rows)
        self._simulate_done(result)
        children = self.app.tree.get_children()
        self.assertEqual(len(children), 3)


# ===========================================================================
# Test: Window Title Updates
# ===========================================================================

class TestWindowTitle(unittest.TestCase):
    """Tests for window title updates reflecting the verdict."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.app._comparing = True
        self.app._compare_start_time = 0.0
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _simulate_done(self, result):
        import time
        self.app._compare_start_time = time.monotonic()
        self.app._on_compare_done(result)
        self.root.update_idletasks()

    def test_title_left_newer(self):
        """Title should show LEFT when score < 0."""
        result = _make_result(score=-5, confidence="Medium")
        self._simulate_done(result)
        title = self.root.title()
        self.assertIn("LEFT", title)
        self.assertIn("newer", title)
        self.assertIn("Medium", title)

    def test_title_right_newer(self):
        """Title should show RIGHT when score > 0."""
        result = _make_result(score=8, confidence="High")
        self._simulate_done(result)
        title = self.root.title()
        self.assertIn("RIGHT", title)
        self.assertIn("newer", title)
        self.assertIn("High", title)

    def test_title_equivalent(self):
        """Title should show Equivalent when score == 0."""
        result = _make_result(score=0, confidence="Low")
        self._simulate_done(result)
        title = self.root.title()
        self.assertIn("Equivalent", title)
        self.assertIn("Low", title)


# ===========================================================================
# Test: Summary Display
# ===========================================================================

class TestSummaryDisplay(unittest.TestCase):
    """Tests for the summary text panel content."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _get_summary_text(self):
        self.app.summary_text.configure(state=tk.NORMAL)
        text = self.app.summary_text.get("1.0", tk.END).strip()
        self.app.summary_text.configure(state=tk.DISABLED)
        return text

    def test_summary_shows_left_verdict(self):
        """Summary should show LEFT verdict for negative score."""
        result = _make_result(
            left_dir="/tmp/left_dir",
            right_dir="/tmp/right_dir",
            score=-5,
            confidence="Medium",
            explanation="Left has more unique files.",
            left_file_count=10,
            right_file_count=8,
            left_total_size=5000,
            right_total_size=4000,
        )
        self.app._update_summary(result)
        self.root.update_idletasks()
        text = self._get_summary_text()
        self.assertIn("VERDICT", text)
        self.assertIn("LEFT", text)
        self.assertIn("left_dir", text)
        self.assertIn("up to date", text)

    def test_summary_shows_right_verdict(self):
        """Summary should show RIGHT verdict for positive score."""
        result = _make_result(
            left_dir="/tmp/left_dir",
            right_dir="/tmp/right_dir",
            score=3,
            confidence="High",
            explanation="Right has newer content.",
            left_file_count=5,
            right_file_count=7,
            left_total_size=1000,
            right_total_size=2000,
        )
        self.app._update_summary(result)
        self.root.update_idletasks()
        text = self._get_summary_text()
        self.assertIn("RIGHT", text)
        self.assertIn("right_dir", text)
        self.assertIn("up to date", text)

    def test_summary_shows_equivalent_verdict(self):
        """Summary should show equivalent verdict for score 0."""
        result = _make_result(score=0, confidence="Low", explanation="No differences.")
        self.app._update_summary(result)
        self.root.update_idletasks()
        text = self._get_summary_text()
        self.assertIn("equivalent", text.lower())

    def test_summary_shows_file_counts(self):
        """Summary should display file counts."""
        result = _make_result(
            left_file_count=42,
            right_file_count=37,
            left_total_size=1024,
            right_total_size=2048,
        )
        self.app._update_summary(result)
        text = self._get_summary_text()
        self.assertIn("42 files", text)
        self.assertIn("37 files", text)

    def test_summary_shows_warnings(self):
        """Summary should display warnings."""
        result = _make_result(
            warnings=["Content heuristic was used for 3 files."]
        )
        self.app._update_summary(result)
        text = self._get_summary_text()
        self.assertIn("WARNING", text)
        self.assertIn("Content heuristic", text)

    def test_summary_shows_multiple_warnings(self):
        """Summary should display multiple warnings."""
        result = _make_result(
            warnings=["Warning one", "Warning two"]
        )
        self.app._update_summary(result)
        text = self._get_summary_text()
        self.assertIn("Warning one", text)
        self.assertIn("Warning two", text)

    def test_summary_shows_explanation(self):
        """Summary should show the explanation text."""
        result = _make_result(explanation="Left has 5 unique file(s).")
        self.app._update_summary(result)
        text = self._get_summary_text()
        self.assertIn("Left has 5 unique file(s)", text)

    def test_summary_shows_file_types(self):
        """Summary should display file type counts if available."""
        result = _make_result(
            file_type_counts={".py": 10, ".txt": 5, ".json": 3}
        )
        self.app._update_summary(result)
        text = self._get_summary_text()
        self.assertIn("File types", text)
        self.assertIn(".py", text)
        self.assertIn(".txt", text)

    def test_summary_no_file_types_when_empty(self):
        """Summary should not show file types line when empty."""
        result = _make_result(file_type_counts={})
        self.app._update_summary(result)
        text = self._get_summary_text()
        self.assertNotIn("File types:", text)

    def test_summary_shows_confidence_and_score(self):
        """Summary should show score and confidence in verdict line."""
        result = _make_result(score=7, confidence="High")
        self.app._update_summary(result)
        text = self._get_summary_text()
        self.assertIn("score: 7", text)
        self.assertIn("confidence: High", text)

    def test_summary_shows_sizes(self):
        """Summary should display formatted sizes."""
        result = _make_result(
            left_total_size=1048576,   # 1 MB
            right_total_size=2097152,  # 2 MB
        )
        self.app._update_summary(result)
        text = self._get_summary_text()
        self.assertIn("1.0 MB", text)
        self.assertIn("2.0 MB", text)


# ===========================================================================
# Test: Copy Summary
# ===========================================================================

class TestCopySummary(unittest.TestCase):
    """Tests for copying the summary text to clipboard."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_copy_summary_empty(self):
        """Copying an empty summary should not raise."""
        self.app._copy_summary()

    def test_copy_summary_with_content(self):
        """Copying summary should put text on the clipboard."""
        result = _make_result(
            score=-3,
            confidence="Medium",
            explanation="Test explanation.",
        )
        self.app._update_summary(result)
        self.root.update_idletasks()
        self.app._copy_summary()
        clipboard = self.root.clipboard_get()
        self.assertIn("VERDICT", clipboard)


# ===========================================================================
# Test: Filter Logic
# ===========================================================================

class TestFilterLogic(unittest.TestCase):
    """Tests for status filter checkboxes and search filtering."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.app.all_rows = [
            _make_row(rel_path="identical.txt", status=FileStatus.IDENTICAL),
            _make_row(rel_path="left_only.txt", status=FileStatus.LEFT_ONLY),
            _make_row(rel_path="right_only.txt", status=FileStatus.RIGHT_ONLY),
            _make_row(rel_path="left_newer.txt", status=FileStatus.LEFT_NEWER),
            _make_row(rel_path="right_newer.txt", status=FileStatus.RIGHT_NEWER),
            _make_row(rel_path="unknown.txt", status=FileStatus.UNKNOWN),
        ]
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _count_tree_items(self):
        return len(self.app.tree.get_children())

    def test_all_filters_on_shows_all(self):
        """All filters on should show all rows."""
        self.app._apply_filters()
        self.assertEqual(self._count_tree_items(), 6)

    def test_uncheck_identical_hides_identical(self):
        """Unchecking 'Identical' should hide identical rows."""
        self.app._filter_vars[FileStatus.IDENTICAL.value].set(False)
        self.app._apply_filters()
        self.assertEqual(self._count_tree_items(), 5)

    def test_only_identical_filter(self):
        """Only checking 'Identical' should show just identical rows."""
        for status in FileStatus:
            self.app._filter_vars[status.value].set(
                status == FileStatus.IDENTICAL
            )
        self.app._apply_filters()
        self.assertEqual(self._count_tree_items(), 1)
        values = self.app.tree.item(self.app.tree.get_children()[0], "values")
        self.assertEqual(values[0], "identical.txt")

    def test_uncheck_all_filters_shows_none(self):
        """Unchecking all filters should show zero rows."""
        for status in FileStatus:
            self.app._filter_vars[status.value].set(False)
        self.app._apply_filters()
        self.assertEqual(self._count_tree_items(), 0)

    def test_filter_updates_showing_label(self):
        """Showing label should update with current count."""
        self.app._apply_filters()
        text = self.app.showing_label.cget("text")
        self.assertIn("6 of 6", text)

    def test_filter_partial_count(self):
        """Filtering some out should update showing label."""
        self.app._filter_vars[FileStatus.IDENTICAL.value].set(False)
        self.app._filter_vars[FileStatus.UNKNOWN.value].set(False)
        self.app._apply_filters()
        text = self.app.showing_label.cget("text")
        self.assertIn("4 of 6", text)

    def test_filter_with_multiple_identical(self):
        """Multiple rows of the same status should all be filtered together."""
        self.app.all_rows.append(
            _make_row(rel_path="identical2.txt", status=FileStatus.IDENTICAL)
        )
        self.app._filter_vars[FileStatus.IDENTICAL.value].set(False)
        self.app._apply_filters()
        # 6 original - 1 identical + 1 added identical - 1 = 5
        self.assertEqual(self._count_tree_items(), 5)


# ===========================================================================
# Test: Search Filtering
# ===========================================================================

class TestSearchFiltering(unittest.TestCase):
    """Tests for the text search feature."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.app.all_rows = [
            _make_row(rel_path="src/main.py", status=FileStatus.IDENTICAL),
            _make_row(rel_path="src/utils.py", status=FileStatus.LEFT_NEWER),
            _make_row(rel_path="tests/test_main.py", status=FileStatus.RIGHT_ONLY),
            _make_row(rel_path="README.md", status=FileStatus.LEFT_ONLY),
            _make_row(rel_path="docs/api.md", status=FileStatus.IDENTICAL),
        ]
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _count_tree_items(self):
        return len(self.app.tree.get_children())

    def test_empty_search_shows_all(self):
        """Empty search string should show all (filtered) rows."""
        self.app.search_var.set("")
        self.app._apply_filters()
        self.assertEqual(self._count_tree_items(), 5)

    def test_search_by_filename(self):
        """Searching for 'main' should match files containing 'main'."""
        self.app.search_var.set("main")
        self.app._apply_filters()
        self.assertEqual(self._count_tree_items(), 2)  # main.py and test_main.py

    def test_search_by_extension(self):
        """Searching for '.md' should match markdown files."""
        self.app.search_var.set(".md")
        self.app._apply_filters()
        self.assertEqual(self._count_tree_items(), 2)  # README.md and api.md

    def test_search_by_directory(self):
        """Searching for 'src/' should match files in src directory."""
        self.app.search_var.set("src/")
        self.app._apply_filters()
        self.assertEqual(self._count_tree_items(), 2)  # main.py and utils.py

    def test_search_is_case_insensitive(self):
        """Search should be case-insensitive."""
        self.app.search_var.set("README")
        self.app._apply_filters()
        self.assertEqual(self._count_tree_items(), 1)

        self.app.search_var.set("readme")
        self.app._apply_filters()
        self.assertEqual(self._count_tree_items(), 1)

    def test_search_no_match(self):
        """Searching for nonexistent term should show nothing."""
        self.app.search_var.set("nonexistent_file_xyz")
        self.app._apply_filters()
        self.assertEqual(self._count_tree_items(), 0)

    def test_search_combined_with_filter(self):
        """Search and status filters should work together."""
        # Disable IDENTICAL filter and search for '.py'
        self.app._filter_vars[FileStatus.IDENTICAL.value].set(False)
        self.app.search_var.set(".py")
        self.app._apply_filters()
        # src/utils.py (LEFT_NEWER) and tests/test_main.py (RIGHT_ONLY)
        # src/main.py is IDENTICAL and filtered out
        self.assertEqual(self._count_tree_items(), 2)

    def test_search_updates_showing_label(self):
        """Showing label should reflect search-filtered counts."""
        self.app.search_var.set("main")
        self.app._apply_filters()
        text = self.app.showing_label.cget("text")
        self.assertIn("2 of 5", text)


# ===========================================================================
# Test: Sort Columns
# ===========================================================================

class TestSortColumn(unittest.TestCase):
    """Tests for the column sorting functionality."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.app.all_rows = [
            _make_row(rel_path="charlie.txt", status=FileStatus.IDENTICAL, size_left=300, size_right=300),
            _make_row(rel_path="alpha.txt", status=FileStatus.LEFT_ONLY, size_left=100, size_right=None),
            _make_row(rel_path="bravo.txt", status=FileStatus.RIGHT_ONLY, size_left=None, size_right=200),
        ]
        self.app._apply_filters()
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _get_tree_values(self, col_idx=0):
        """Get all values from the treeview at the given column index."""
        result = []
        for child in self.app.tree.get_children():
            vals = self.app.tree.item(child, "values")
            result.append(vals[col_idx])
        return result

    def test_sort_by_rel_path_ascending(self):
        """Sorting by rel_path ascending should give alphabetical order."""
        self.app._sort_column("rel_path")
        paths = self._get_tree_values(0)
        self.assertEqual(paths[0], "alpha.txt")
        self.assertEqual(paths[1], "bravo.txt")
        self.assertEqual(paths[2], "charlie.txt")

    def test_sort_by_rel_path_descending(self):
        """Double-sorting by rel_path should give reverse alphabetical order."""
        self.app._sort_column("rel_path")
        self.app._sort_column("rel_path")
        paths = self._get_tree_values(0)
        self.assertEqual(paths[0], "charlie.txt")
        self.assertEqual(paths[1], "bravo.txt")
        self.assertEqual(paths[2], "alpha.txt")

    def test_sort_toggle_reverse(self):
        """Sorting should toggle the reverse flag each time."""
        self.assertFalse(self.app._sort_reverse.get("rel_path", False))
        self.app._sort_column("rel_path")
        self.assertTrue(self.app._sort_reverse["rel_path"])
        self.app._sort_column("rel_path")
        self.assertFalse(self.app._sort_reverse["rel_path"])

    def test_sort_by_status(self):
        """Sorting by status should order by status text."""
        self.app._sort_column("status")
        statuses = self._get_tree_values(1)
        self.assertEqual(statuses, sorted(statuses, key=str.lower))

    def test_sort_updates_heading_arrow(self):
        """Sorted column heading should display an arrow indicator."""
        self.app._sort_column("rel_path")
        self.root.update_idletasks()
        heading_text = self.app.tree.heading("rel_path", "text")
        # After first sort (ascending), arrow should be present
        has_arrow = "\u25b2" in heading_text or "\u25bc" in heading_text
        self.assertTrue(has_arrow, f"Expected arrow in heading, got: {heading_text}")

    def test_sort_different_column_clears_previous_arrow(self):
        """Sorting a new column should remove arrow from the previous column."""
        self.app._sort_column("rel_path")
        self.app._sort_column("status")
        self.root.update_idletasks()
        path_heading = self.app.tree.heading("rel_path", "text")
        self.assertNotIn("\u25b2", path_heading)
        self.assertNotIn("\u25bc", path_heading)

    def test_sort_size_left_numeric(self):
        """Size columns should sort numerically, not lexicographically."""
        self.app._sort_column("size_left")
        sizes = self._get_tree_values(2)
        # "-" (None) should sort before numeric values
        self.assertEqual(sizes[0], "-")


# ===========================================================================
# Test: Filter Label Updates
# ===========================================================================

class TestFilterLabelUpdates(unittest.TestCase):
    """Tests for the filter checkbox label updates with counts."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_filter_labels_show_counts(self):
        """Filter labels should show counts after comparison."""
        result = _make_result(
            status_counts={
                FileStatus.IDENTICAL.value: 10,
                FileStatus.LEFT_ONLY.value: 3,
                FileStatus.RIGHT_ONLY.value: 2,
                FileStatus.LEFT_NEWER.value: 1,
                FileStatus.RIGHT_NEWER.value: 0,
                FileStatus.UNKNOWN.value: 0,
            }
        )
        self.app._update_filter_labels(result)
        self.root.update_idletasks()

        # Check that the checkbox texts were updated
        identical_text = self.app._filter_cbs[FileStatus.IDENTICAL.value].cget("text")
        self.assertIn("10", identical_text)
        self.assertIn("Identical", identical_text)

        left_only_text = self.app._filter_cbs[FileStatus.LEFT_ONLY.value].cget("text")
        self.assertIn("3", left_only_text)

    def test_filter_labels_zero_counts(self):
        """Filter labels should show (0) for empty counts."""
        result = _make_result(status_counts={})
        self.app._update_filter_labels(result)
        self.root.update_idletasks()

        for status in FileStatus:
            text = self.app._filter_cbs[status.value].cget("text")
            self.assertIn("(0)", text)


# ===========================================================================
# Test: Column Heading Updates
# ===========================================================================

class TestColumnHeadingUpdates(unittest.TestCase):
    """Tests for dynamic column heading updates with directory names."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_column_headings_show_directory_names(self):
        """Size column headings should include directory basenames."""
        result = _make_result(
            left_dir="/home/user/project_v1",
            right_dir="/home/user/project_v2",
        )
        self.app._update_column_headings(result)
        self.root.update_idletasks()

        left_heading = self.app.tree.heading("size_left", "text")
        right_heading = self.app.tree.heading("size_right", "text")
        self.assertIn("project_v1", left_heading)
        self.assertIn("project_v2", right_heading)

    def test_column_headings_fallback(self):
        """When basenames are empty, headings should use 'Left'/'Right' fallback."""
        # This would happen if the dir is "/" or similar
        result = _make_result(left_dir="/", right_dir="/")
        self.app._update_column_headings(result)
        self.root.update_idletasks()
        left_heading = self.app.tree.heading("size_left", "text")
        right_heading = self.app.tree.heading("size_right", "text")
        # os.path.basename("/") returns "" so the fallback "Left"/"Right" is used
        self.assertIn("Left", left_heading)
        self.assertIn("Right", right_heading)


# ===========================================================================
# Test: Ignore Pattern Summary
# ===========================================================================

class TestIgnorePatternSummary(unittest.TestCase):
    """Tests for the ignore pattern summary label."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_default_ignore_summary_count(self):
        """Default ignore patterns should produce a non-zero count."""
        text = self.app._ignore_summary()
        self.assertIn("patterns", text)
        # Extract the number and check it is > 0
        num = int(text.split()[0])
        self.assertGreater(num, 0)

    def test_ignore_summary_with_custom_patterns(self):
        """Custom patterns should reflect correct count."""
        self.app.ignore_var.set("*.pyc, __pycache__, .git")
        text = self.app._ignore_summary()
        self.assertIn("3 patterns", text)

    def test_ignore_summary_empty(self):
        """Empty ignore patterns should show 0 patterns."""
        self.app.ignore_var.set("")
        text = self.app._ignore_summary()
        self.assertIn("0 patterns", text)

    def test_ignore_summary_with_whitespace_only(self):
        """Whitespace-only patterns should count as 0."""
        self.app.ignore_var.set("  ,  ,  ")
        text = self.app._ignore_summary()
        self.assertIn("0 patterns", text)


# ===========================================================================
# Test: Treeview Row Tags
# ===========================================================================

class TestTreeviewRowTags(unittest.TestCase):
    """Tests that rows in the treeview get the correct colour tags."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_identical_row_has_tag(self):
        """Identical rows should have the 'identical' tag."""
        self.app.all_rows = [
            _make_row(rel_path="same.txt", status=FileStatus.IDENTICAL),
        ]
        self.app._apply_filters()
        children = self.app.tree.get_children()
        self.assertEqual(len(children), 1)
        tags = self.app.tree.item(children[0], "tags")
        self.assertIn("identical", tags)

    def test_left_only_row_has_tag(self):
        """Left-only rows should have the 'left_only' tag."""
        self.app.all_rows = [
            _make_row(rel_path="only_left.txt", status=FileStatus.LEFT_ONLY),
        ]
        self.app._apply_filters()
        children = self.app.tree.get_children()
        tags = self.app.tree.item(children[0], "tags")
        self.assertIn("left_only", tags)

    def test_right_only_row_has_tag(self):
        """Right-only rows should have the 'right_only' tag."""
        self.app.all_rows = [
            _make_row(rel_path="only_right.txt", status=FileStatus.RIGHT_ONLY),
        ]
        self.app._apply_filters()
        children = self.app.tree.get_children()
        tags = self.app.tree.item(children[0], "tags")
        self.assertIn("right_only", tags)

    def test_all_statuses_get_tags(self):
        """Every FileStatus should produce a row with the corresponding tag."""
        self.app.all_rows = [
            _make_row(rel_path=f"file_{s.name}.txt", status=s)
            for s in FileStatus
        ]
        self.app._apply_filters()
        children = self.app.tree.get_children()
        self.assertEqual(len(children), len(FileStatus))
        for child in children:
            tags = self.app.tree.item(child, "tags")
            vals = self.app.tree.item(child, "values")
            status_val = vals[1]
            expected_tag = DirCompareApp.STATUS_TAGS[status_val][0]
            self.assertIn(expected_tag, tags)


# ===========================================================================
# Test: Treeview Row Values
# ===========================================================================

class TestTreeviewRowValues(unittest.TestCase):
    """Tests that treeview rows display correct values."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_row_displays_correct_path(self):
        """Treeview row should show the relative path."""
        self.app.all_rows = [
            _make_row(rel_path="src/main.py", status=FileStatus.IDENTICAL),
        ]
        self.app._apply_filters()
        children = self.app.tree.get_children()
        vals = self.app.tree.item(children[0], "values")
        self.assertEqual(vals[0], "src/main.py")

    def test_row_displays_status(self):
        """Treeview row should show the status text."""
        self.app.all_rows = [
            _make_row(rel_path="f.txt", status=FileStatus.LEFT_NEWER),
        ]
        self.app._apply_filters()
        children = self.app.tree.get_children()
        vals = self.app.tree.item(children[0], "values")
        self.assertEqual(vals[1], "Left Newer")

    def test_row_displays_formatted_sizes(self):
        """Treeview row should show human-readable sizes."""
        self.app.all_rows = [
            _make_row(
                rel_path="big.dat",
                status=FileStatus.IDENTICAL,
                size_left=1048576,   # 1 MB
                size_right=2097152,  # 2 MB
            ),
        ]
        self.app._apply_filters()
        children = self.app.tree.get_children()
        vals = self.app.tree.item(children[0], "values")
        self.assertEqual(vals[2], "1.0 MB")
        self.assertEqual(vals[3], "2.0 MB")

    def test_row_displays_dash_for_missing_size(self):
        """Missing sizes (None) should be displayed as '-'."""
        self.app.all_rows = [
            _make_row(rel_path="left.txt", status=FileStatus.LEFT_ONLY,
                      size_left=500, size_right=None),
        ]
        self.app._apply_filters()
        children = self.app.tree.get_children()
        vals = self.app.tree.item(children[0], "values")
        self.assertEqual(vals[3], "-")

    def test_row_displays_notes(self):
        """Treeview row should show notes text."""
        self.app.all_rows = [
            _make_row(rel_path="x.txt", status=FileStatus.LEFT_NEWER,
                      notes="Left has more content"),
        ]
        self.app._apply_filters()
        children = self.app.tree.get_children()
        vals = self.app.tree.item(children[0], "values")
        self.assertEqual(vals[4], "Left has more content")


# ===========================================================================
# Test: DiffViewer
# ===========================================================================

class TestDiffViewer(unittest.TestCase):
    """Tests for the DiffViewer toplevel window."""

    def setUp(self):
        self.root = _create_tk_root()
        self._tmpdir = tempfile.mkdtemp()
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        # Clean up temp files
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        path = os.path.join(self._tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _write_binary_file(self, name, content):
        path = os.path.join(self._tmpdir, name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def test_diff_viewer_title(self):
        """DiffViewer window title should include the relative path."""
        left = self._write_file("left.txt", "hello\n")
        right = self._write_file("right.txt", "hello\n")
        dv = DiffViewer(self.root, left, right, "test/file.txt")
        self.root.update_idletasks()
        self.assertIn("test/file.txt", dv.title())
        dv.destroy()

    def test_diff_identical_files(self):
        """DiffViewer should show 'Files are identical' for same content."""
        left = self._write_file("left.txt", "same content\n")
        right = self._write_file("right.txt", "same content\n")
        dv = DiffViewer(self.root, left, right, "same.txt")
        self.root.update_idletasks()
        dv.text.configure(state=tk.NORMAL)
        text = dv.text.get("1.0", tk.END).strip()
        dv.text.configure(state=tk.DISABLED)
        self.assertIn("identical", text.lower())
        dv.destroy()

    def test_diff_different_files(self):
        """DiffViewer should show diff output for different files."""
        left = self._write_file("left.txt", "line one\nline two\n")
        right = self._write_file("right.txt", "line one\nline three\n")
        dv = DiffViewer(self.root, left, right, "diff.txt")
        self.root.update_idletasks()
        dv.text.configure(state=tk.NORMAL)
        text = dv.text.get("1.0", tk.END).strip()
        dv.text.configure(state=tk.DISABLED)
        # Diff should contain +/- markers
        self.assertIn("---", text)
        self.assertIn("+++", text)
        dv.destroy()

    def test_diff_binary_files(self):
        """DiffViewer should show binary message for binary files."""
        left = self._write_binary_file("left.bin", b"\x00\x01\x02\x03")
        right = self._write_binary_file("right.bin", b"\x00\x04\x05\x06")
        dv = DiffViewer(self.root, left, right, "data.bin")
        self.root.update_idletasks()
        dv.text.configure(state=tk.NORMAL)
        text = dv.text.get("1.0", tk.END).strip()
        dv.text.configure(state=tk.DISABLED)
        self.assertIn("Binary file", text)
        dv.destroy()

    def test_diff_left_only(self):
        """DiffViewer should handle left-only file (right does not exist)."""
        left = self._write_file("left.txt", "content\n")
        right = os.path.join(self._tmpdir, "nonexistent_right.txt")
        dv = DiffViewer(self.root, left, right, "leftonly.txt")
        self.root.update_idletasks()
        dv.text.configure(state=tk.NORMAL)
        text = dv.text.get("1.0", tk.END).strip()
        dv.text.configure(state=tk.DISABLED)
        self.assertIn("left side", text.lower())
        dv.destroy()

    def test_diff_right_only(self):
        """DiffViewer should handle right-only file (left does not exist)."""
        left = os.path.join(self._tmpdir, "nonexistent_left.txt")
        right = self._write_file("right.txt", "content\n")
        dv = DiffViewer(self.root, left, right, "rightonly.txt")
        self.root.update_idletasks()
        dv.text.configure(state=tk.NORMAL)
        text = dv.text.get("1.0", tk.END).strip()
        dv.text.configure(state=tk.DISABLED)
        self.assertIn("right side", text.lower())
        dv.destroy()

    def test_diff_neither_exists(self):
        """DiffViewer should handle case where neither file exists."""
        left = os.path.join(self._tmpdir, "nope_left.txt")
        right = os.path.join(self._tmpdir, "nope_right.txt")
        dv = DiffViewer(self.root, left, right, "missing.txt")
        self.root.update_idletasks()
        dv.text.configure(state=tk.NORMAL)
        text = dv.text.get("1.0", tk.END).strip()
        dv.text.configure(state=tk.DISABLED)
        self.assertIn("Neither file exists", text)
        dv.destroy()

    def test_diff_viewer_text_is_readonly(self):
        """DiffViewer text widget should be in DISABLED (read-only) state."""
        left = self._write_file("left.txt", "a\n")
        right = self._write_file("right.txt", "a\n")
        dv = DiffViewer(self.root, left, right, "ro.txt")
        self.root.update_idletasks()
        state = str(dv.text.cget("state"))
        self.assertEqual(state, "disabled")
        dv.destroy()

    def test_diff_viewer_has_scrollbars(self):
        """DiffViewer should have a text widget and scrollbars."""
        left = self._write_file("left.txt", "a\n")
        right = self._write_file("right.txt", "b\n")
        dv = DiffViewer(self.root, left, right, "scroll.txt")
        self.root.update_idletasks()
        self.assertIsInstance(dv.text, tk.Text)
        dv.destroy()

    def test_diff_with_none_paths(self):
        """DiffViewer should handle None left_path (right only)."""
        right = self._write_file("right.txt", "content\n")
        dv = DiffViewer(self.root, None, right, "none_left.txt")
        self.root.update_idletasks()
        dv.text.configure(state=tk.NORMAL)
        text = dv.text.get("1.0", tk.END).strip()
        dv.text.configure(state=tk.DISABLED)
        self.assertIn("right side", text.lower())
        dv.destroy()

    def test_diff_with_empty_string_paths(self):
        """DiffViewer should handle empty string paths."""
        dv = DiffViewer(self.root, "", "", "empty.txt")
        self.root.update_idletasks()
        dv.text.configure(state=tk.NORMAL)
        text = dv.text.get("1.0", tk.END).strip()
        dv.text.configure(state=tk.DISABLED)
        self.assertIn("Neither file exists", text)
        dv.destroy()


# ===========================================================================
# Test: IgnorePatternsDialog Categories
# ===========================================================================

class TestIgnorePatternsDialogCategories(unittest.TestCase):
    """Tests for the IgnorePatternsDialog category definitions."""

    def test_categories_exist(self):
        """CATEGORIES dict should have expected keys."""
        cats = IgnorePatternsDialog.CATEGORIES
        self.assertIn("Python", cats)
        self.assertIn("JavaScript/Node", cats)
        self.assertIn("Version Control", cats)
        self.assertIn("OS Artifacts", cats)
        self.assertIn("IDE/Editor", cats)

    def test_python_category_patterns(self):
        """Python category should include __pycache__ and *.pyc."""
        patterns = IgnorePatternsDialog.CATEGORIES["Python"]
        self.assertIn("__pycache__", patterns)
        self.assertIn("*.pyc", patterns)

    def test_version_control_category(self):
        """Version Control category should include .git."""
        patterns = IgnorePatternsDialog.CATEGORIES["Version Control"]
        self.assertIn(".git", patterns)

    def test_all_categories_have_non_empty_patterns(self):
        """Every category should have at least one pattern."""
        for name, patterns_str in IgnorePatternsDialog.CATEGORIES.items():
            patterns = [p.strip() for p in patterns_str.split(",") if p.strip()]
            self.assertGreater(len(patterns), 0, f"Category '{name}' has no patterns")

    def test_category_count(self):
        """There should be a reasonable number of categories."""
        cats = IgnorePatternsDialog.CATEGORIES
        self.assertGreaterEqual(len(cats), 10)


# ===========================================================================
# Test: Status Tags Configuration
# ===========================================================================

class TestStatusTags(unittest.TestCase):
    """Tests for the STATUS_TAGS class attribute."""

    def test_all_statuses_have_tags(self):
        """Every FileStatus value should have an entry in STATUS_TAGS."""
        for status in FileStatus:
            self.assertIn(
                status.value,
                DirCompareApp.STATUS_TAGS,
                f"Missing tag for {status.value}",
            )

    def test_tag_format(self):
        """Each tag entry should be a (tag_name, colour_hex) tuple."""
        for status_value, (tag_name, bg_color) in DirCompareApp.STATUS_TAGS.items():
            self.assertIsInstance(tag_name, str)
            self.assertTrue(
                bg_color.startswith("#"),
                f"Background colour for {status_value} should be a hex string",
            )


# ===========================================================================
# Test: Default Ignore Patterns
# ===========================================================================

class TestDefaultIgnorePatterns(unittest.TestCase):
    """Tests for the DEFAULT_IGNORE class attribute."""

    def test_default_ignore_is_string(self):
        """DEFAULT_IGNORE should be a string."""
        self.assertIsInstance(DirCompareApp.DEFAULT_IGNORE, str)

    def test_default_ignore_contains_common_patterns(self):
        """DEFAULT_IGNORE should contain common ignore patterns."""
        patterns = DirCompareApp.DEFAULT_IGNORE
        for expected in ["__pycache__", "node_modules", ".git", ".DS_Store", "Thumbs.db"]:
            self.assertIn(expected, patterns)

    def test_default_ignore_parseable(self):
        """DEFAULT_IGNORE should be parseable into individual patterns."""
        raw = DirCompareApp.DEFAULT_IGNORE
        patterns = [p.strip() for p in raw.split(",") if p.strip()]
        self.assertGreater(len(patterns), 20)


# ===========================================================================
# Test: Comprehensive On Compare Done Scenarios
# ===========================================================================

class TestOnCompareDoneScenarios(unittest.TestCase):
    """Tests for various comparison result scenarios flowing through _on_compare_done."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.app._comparing = True
        self.app._compare_start_time = 0.0
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _simulate_done(self, result):
        import time
        self.app._compare_start_time = time.monotonic()
        self.app._on_compare_done(result)
        self.root.update_idletasks()

    def test_empty_comparison(self):
        """Empty comparison with no rows should display correctly."""
        result = _make_result(rows=[], score=0, confidence="Low")
        self._simulate_done(result)
        children = self.app.tree.get_children()
        self.assertEqual(len(children), 0)
        text = self.app.showing_label.cget("text")
        self.assertIn("0 of 0", text)

    def test_large_positive_score(self):
        """Large positive score should show HIGH confidence."""
        result = _make_result(
            score=10,
            confidence="High",
            rows=[
                _make_row(rel_path=f"file{i}.txt", status=FileStatus.RIGHT_ONLY)
                for i in range(10)
            ],
        )
        self._simulate_done(result)
        title = self.root.title()
        self.assertIn("RIGHT", title)
        self.assertIn("High", title)

    def test_large_negative_score(self):
        """Large negative score should show LEFT newer."""
        result = _make_result(
            score=-12,
            confidence="High",
            rows=[
                _make_row(rel_path=f"file{i}.txt", status=FileStatus.LEFT_ONLY)
                for i in range(12)
            ],
        )
        self._simulate_done(result)
        title = self.root.title()
        self.assertIn("LEFT", title)

    def test_mixed_statuses(self):
        """Rows with mixed statuses should all appear in treeview."""
        rows = [
            _make_row(rel_path="a.txt", status=FileStatus.IDENTICAL),
            _make_row(rel_path="b.txt", status=FileStatus.LEFT_ONLY),
            _make_row(rel_path="c.txt", status=FileStatus.RIGHT_ONLY),
            _make_row(rel_path="d.txt", status=FileStatus.LEFT_NEWER),
            _make_row(rel_path="e.txt", status=FileStatus.RIGHT_NEWER),
            _make_row(rel_path="f.txt", status=FileStatus.UNKNOWN),
        ]
        result = _make_result(rows=rows, score=2, confidence="Medium")
        self._simulate_done(result)
        self.assertEqual(len(self.app.tree.get_children()), 6)

    def test_result_with_timestamp(self):
        """Result with timestamp should be stored properly."""
        result = _make_result(timestamp="2026-02-28 15:30:00")
        self._simulate_done(result)
        self.assertEqual(self.app.result.timestamp, "2026-02-28 15:30:00")

    def test_result_with_file_type_counts(self):
        """Result with file type counts should display in summary."""
        result = _make_result(
            file_type_counts={".py": 15, ".js": 8, ".css": 3},
            score=0,
            confidence="Low",
        )
        self._simulate_done(result)
        self.app.summary_text.configure(state=tk.NORMAL)
        text = self.app.summary_text.get("1.0", tk.END)
        self.app.summary_text.configure(state=tk.DISABLED)
        self.assertIn(".py", text)

    def test_result_with_git_commits(self):
        """Result with git commit counts should be stored."""
        result = _make_result(left_git_commits=100, right_git_commits=150)
        self._simulate_done(result)
        self.assertEqual(self.app.result.left_git_commits, 100)
        self.assertEqual(self.app.result.right_git_commits, 150)

    def test_result_with_versions(self):
        """Result with version strings should be stored."""
        result = _make_result(
            left_versions=["1.0.0", "2.0.0"],
            right_versions=["1.0.0", "3.0.0"],
        )
        self._simulate_done(result)
        self.assertEqual(self.app.result.left_versions, ["1.0.0", "2.0.0"])

    def test_result_with_custom_weights(self):
        """Result with custom weights should be stored."""
        w = ScoringWeights(unique_file=5, content_analysis=3, version_string=4, git_commits=1)
        result = _make_result(weights=w)
        self._simulate_done(result)
        self.assertEqual(self.app.result.weights.unique_file, 5)


# ===========================================================================
# Test: _apply_filters Interactions
# ===========================================================================

class TestApplyFiltersEdgeCases(unittest.TestCase):
    """Edge case tests for _apply_filters."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_apply_filters_clears_tree_first(self):
        """_apply_filters should clear all existing treeview items first."""
        # Insert some dummy items
        self.app.all_rows = [
            _make_row(rel_path="old.txt", status=FileStatus.IDENTICAL),
        ]
        self.app._apply_filters()
        self.assertEqual(len(self.app.tree.get_children()), 1)

        # Now set empty rows and filter again
        self.app.all_rows = []
        self.app._apply_filters()
        self.assertEqual(len(self.app.tree.get_children()), 0)

    def test_apply_filters_with_special_chars_in_path(self):
        """Rows with special characters in paths should display correctly."""
        self.app.all_rows = [
            _make_row(rel_path="dir with spaces/file (1).txt", status=FileStatus.IDENTICAL),
            _make_row(rel_path="dir/file-with-dashes.txt", status=FileStatus.LEFT_ONLY),
        ]
        self.app._apply_filters()
        self.assertEqual(len(self.app.tree.get_children()), 2)

    def test_search_with_special_regex_chars(self):
        """Search with regex special chars should be treated as literal text."""
        self.app.all_rows = [
            _make_row(rel_path="file (1).txt", status=FileStatus.IDENTICAL),
            _make_row(rel_path="file.txt", status=FileStatus.LEFT_ONLY),
        ]
        # Parentheses should be treated as literal
        self.app.search_var.set("(1)")
        self.app._apply_filters()
        self.assertEqual(len(self.app.tree.get_children()), 1)


# ===========================================================================
# Test: Update Progress
# ===========================================================================

class TestUpdateProgress(unittest.TestCase):
    """Tests for the progress update mechanism."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_update_progress_zero(self):
        """Progress at 0 should set bar to 0."""
        self.app._update_progress(0.0)
        self.assertAlmostEqual(self.app.progress_var.get(), 0.0)

    def test_update_progress_half(self):
        """Progress at 0.5 should set bar to 50."""
        self.app._update_progress(0.5)
        self.assertAlmostEqual(self.app.progress_var.get(), 50.0)

    def test_update_progress_full(self):
        """Progress at 1.0 should set bar to 100."""
        self.app._update_progress(1.0)
        self.assertAlmostEqual(self.app.progress_var.get(), 100.0)

    def test_update_progress_clamps_at_100(self):
        """Progress beyond 1.0 should be clamped to 100."""
        self.app._update_progress(1.5)
        self.assertAlmostEqual(self.app.progress_var.get(), 100.0)

    def test_update_progress_updates_status_label(self):
        """Status label should show the percentage."""
        self.app._update_progress(0.75)
        text = self.app.status_label.cget("text")
        self.assertIn("75", text)


# ===========================================================================
# Test: On Compare Error
# ===========================================================================

class TestOnCompareError(unittest.TestCase):
    """Tests for the error handling in comparison."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.app._comparing = True
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_error_resets_comparing_flag(self):
        """Error should reset the comparing flag."""
        # Patch messagebox to avoid the dialog blocking
        import unittest.mock
        with unittest.mock.patch("DirCompare.gui.messagebox.showerror"):
            self.app._on_compare_error("test error")
        self.assertFalse(self.app._comparing)

    def test_error_re_enables_compare_button(self):
        """Error should re-enable the compare button."""
        import unittest.mock
        with unittest.mock.patch("DirCompare.gui.messagebox.showerror"):
            self.app._on_compare_error("test error")
        state = str(self.app.compare_btn.cget("state"))
        self.assertNotIn("disabled", state)

    def test_error_disables_cancel_button(self):
        """Error should disable the cancel button."""
        import unittest.mock
        with unittest.mock.patch("DirCompare.gui.messagebox.showerror"):
            self.app._on_compare_error("test error")
        state = str(self.app.cancel_btn.cget("state"))
        self.assertIn("disabled", state)

    def test_error_resets_progress(self):
        """Error should reset progress to 0."""
        import unittest.mock
        with unittest.mock.patch("DirCompare.gui.messagebox.showerror"):
            self.app._on_compare_error("test error")
        self.assertAlmostEqual(self.app.progress_var.get(), 0.0)

    def test_error_updates_status_label(self):
        """Error should set status label to 'Error'."""
        import unittest.mock
        with unittest.mock.patch("DirCompare.gui.messagebox.showerror"):
            self.app._on_compare_error("test error")
        text = self.app.status_label.cget("text")
        self.assertEqual(text, "Error")


# ===========================================================================
# Test: Cancel Compare
# ===========================================================================

class TestCancelCompare(unittest.TestCase):
    """Tests for the cancel comparison mechanism."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_cancel_sets_event_when_comparing(self):
        """Cancel should set the cancel event when a comparison is in progress."""
        self.app._comparing = True
        self.app._cancel_compare()
        self.assertTrue(self.app._cancel_event.is_set())

    def test_cancel_does_nothing_when_not_comparing(self):
        """Cancel should be a no-op when not comparing."""
        self.app._comparing = False
        self.app._cancel_event.clear()
        self.app._cancel_compare()
        self.assertFalse(self.app._cancel_event.is_set())

    def test_cancel_updates_status_label(self):
        """Cancel should update status label to 'Cancelling...'."""
        self.app._comparing = True
        self.app._cancel_compare()
        text = self.app.status_label.cget("text")
        self.assertIn("Cancelling", text)


# ===========================================================================
# Test: Recompare
# ===========================================================================

class TestRecompare(unittest.TestCase):
    """Tests for the re-compare functionality."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_recompare_does_nothing_without_dirs(self):
        """Re-compare should be a no-op if directories are not set."""
        self.app.left_var.set("")
        self.app.right_var.set("")
        # Should not raise or start comparing
        self.app._recompare()
        self.assertFalse(self.app._comparing)

    def test_recompare_does_nothing_with_only_left(self):
        """Re-compare should be a no-op with only left directory set."""
        self.app.left_var.set("/some/path")
        self.app.right_var.set("")
        self.app._recompare()
        self.assertFalse(self.app._comparing)


# ===========================================================================
# Test: Copy to Clipboard
# ===========================================================================

class TestCopyToClipboard(unittest.TestCase):
    """Tests for the clipboard copy helper."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_copy_to_clipboard(self):
        """_copy_to_clipboard should set clipboard content."""
        self.app._copy_to_clipboard("/some/test/path")
        clipboard = self.root.clipboard_get()
        self.assertEqual(clipboard, "/some/test/path")

    def test_copy_to_clipboard_replaces_previous(self):
        """Second copy should replace previous clipboard content."""
        self.app._copy_to_clipboard("first")
        self.app._copy_to_clipboard("second")
        clipboard = self.root.clipboard_get()
        self.assertEqual(clipboard, "second")


# ===========================================================================
# Test: _get_selected_row
# ===========================================================================

class TestGetSelectedRow(unittest.TestCase):
    """Tests for _get_selected_row helper."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.app.all_rows = [
            _make_row(rel_path="a.txt", status=FileStatus.IDENTICAL,
                      left_path="/l/a.txt", right_path="/r/a.txt"),
            _make_row(rel_path="b.txt", status=FileStatus.LEFT_ONLY,
                      left_path="/l/b.txt", right_path=None),
        ]
        self.app._apply_filters()
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_no_selection_returns_none(self):
        """With no selection, _get_selected_row should return None."""
        result = self.app._get_selected_row()
        self.assertIsNone(result)

    def test_with_selection_returns_row(self):
        """With a selection, _get_selected_row should return the matching ComparisonRow."""
        children = self.app.tree.get_children()
        self.app.tree.selection_set(children[0])
        row = self.app._get_selected_row()
        self.assertIsNotNone(row)
        self.assertEqual(row.rel_path, "a.txt")

    def test_second_item_selection(self):
        """Selecting the second item should return the second row."""
        children = self.app.tree.get_children()
        self.app.tree.selection_set(children[1])
        row = self.app._get_selected_row()
        self.assertIsNotNone(row)
        self.assertEqual(row.rel_path, "b.txt")


# ===========================================================================
# Test: Search Debounce
# ===========================================================================

class TestSearchDebounce(unittest.TestCase):
    """Tests for the search debounce mechanism."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_schedule_search_creates_after_id(self):
        """_schedule_search should create a pending after callback."""
        self.app._schedule_search()
        self.assertIsNotNone(self.app._search_after_id)

    def test_schedule_search_cancels_previous(self):
        """Consecutive calls should cancel the previous scheduled callback."""
        self.app._schedule_search()
        first_id = self.app._search_after_id
        self.app._schedule_search()
        second_id = self.app._search_after_id
        # The IDs should be different (old one cancelled, new one created)
        self.assertNotEqual(first_id, second_id)


# ===========================================================================
# Test: Sort Column with Result (dynamic headings)
# ===========================================================================

class TestSortColumnWithResult(unittest.TestCase):
    """Tests for sorting after a comparison has been done, with dynamic column names."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.app._comparing = True
        self.app._compare_start_time = 0.0
        rows = [
            _make_row(rel_path="z.txt", status=FileStatus.IDENTICAL, size_left=500, size_right=500),
            _make_row(rel_path="a.txt", status=FileStatus.LEFT_ONLY, size_left=100, size_right=None),
            _make_row(rel_path="m.txt", status=FileStatus.RIGHT_ONLY, size_left=None, size_right=300),
        ]
        result = _make_result(
            left_dir="/home/user/projA",
            right_dir="/home/user/projB",
            rows=rows,
        )
        import time
        self.app._compare_start_time = time.monotonic()
        self.app._on_compare_done(result)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_sort_preserves_dynamic_heading_names(self):
        """Sorting should preserve the dynamic 'Size (projA)' / 'Size (projB)' headings."""
        self.app._sort_column("rel_path")
        self.root.update_idletasks()
        left_h = self.app.tree.heading("size_left", "text")
        right_h = self.app.tree.heading("size_right", "text")
        self.assertIn("projA", left_h)
        self.assertIn("projB", right_h)

    def test_sort_by_size_numeric_ordering(self):
        """Sorting by size_left should use numeric ordering."""
        self.app._sort_column("size_left")
        self.root.update_idletasks()
        children = self.app.tree.get_children()
        first_val = self.app.tree.item(children[0], "values")[2]
        # "-" (None mapped) should sort first when ascending (it maps to -1)
        self.assertEqual(first_val, "-")


# ===========================================================================
# Test: Summary Text Tag Existence
# ===========================================================================

class TestSummaryTextTags(unittest.TestCase):
    """Tests that the summary text widget has the correct tags configured."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_verdict_high_tag(self):
        """verdict_high tag should exist in summary widget."""
        config = self.app.summary_text.tag_configure("verdict_high")
        self.assertIsNotNone(config)

    def test_verdict_medium_tag(self):
        """verdict_medium tag should exist in summary widget."""
        config = self.app.summary_text.tag_configure("verdict_medium")
        self.assertIsNotNone(config)

    def test_verdict_low_tag(self):
        """verdict_low tag should exist in summary widget."""
        config = self.app.summary_text.tag_configure("verdict_low")
        self.assertIsNotNone(config)

    def test_warning_tag(self):
        """warning tag should exist in summary widget."""
        config = self.app.summary_text.tag_configure("warning")
        self.assertIsNotNone(config)


# ===========================================================================
# Test: Full Flow (compare done -> filter -> sort -> search)
# ===========================================================================

class TestFullFlow(unittest.TestCase):
    """Integration-style test exercising the full flow of data through the GUI."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.app._comparing = True
        self.app._compare_start_time = 0.0
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_full_flow(self):
        """Full flow: load result, check summary, filter, search, sort."""
        import time
        rows = [
            _make_row(rel_path="src/app.py", status=FileStatus.LEFT_NEWER, size_left=2000, size_right=1500),
            _make_row(rel_path="src/utils.py", status=FileStatus.IDENTICAL, size_left=500, size_right=500),
            _make_row(rel_path="README.md", status=FileStatus.RIGHT_ONLY, size_left=None, size_right=800),
            _make_row(rel_path="tests/test_app.py", status=FileStatus.LEFT_ONLY, size_left=1200, size_right=None),
            _make_row(rel_path="config.json", status=FileStatus.RIGHT_NEWER, size_left=100, size_right=150),
        ]
        result = _make_result(
            left_dir="/projects/v1",
            right_dir="/projects/v2",
            rows=rows,
            score=-3,
            confidence="Medium",
            explanation="Left has newer content in 1 file. Left has 1 unique file.",
            warnings=["Content heuristic used for 1 file."],
            left_file_count=4,
            right_file_count=4,
            left_total_size=3800,
            right_total_size=2950,
            status_counts={
                "Left Newer": 1, "Identical": 1, "Right Only": 1,
                "Left Only": 1, "Right Newer": 1, "Unknown": 0,
            },
            file_type_counts={".py": 3, ".md": 1, ".json": 1},
            timestamp="2026-02-28 10:00:00",
        )

        # Step 1: Load result
        self.app._compare_start_time = time.monotonic()
        self.app._on_compare_done(result)
        self.root.update_idletasks()

        # Verify all 5 rows appear
        self.assertEqual(len(self.app.tree.get_children()), 5)

        # Check summary contains verdict
        self.app.summary_text.configure(state=tk.NORMAL)
        summary = self.app.summary_text.get("1.0", tk.END)
        self.app.summary_text.configure(state=tk.DISABLED)
        self.assertIn("LEFT", summary)
        self.assertIn("WARNING", summary)
        self.assertIn(".py", summary)

        # Check title
        title = self.root.title()
        self.assertIn("LEFT", title)
        self.assertIn("Medium", title)

        # Step 2: Filter out identical
        self.app._filter_vars[FileStatus.IDENTICAL.value].set(False)
        self.app._apply_filters()
        self.root.update_idletasks()
        self.assertEqual(len(self.app.tree.get_children()), 4)

        # Step 3: Search for .py files
        self.app.search_var.set(".py")
        self.app._apply_filters()
        self.root.update_idletasks()
        # Should show app.py and test_app.py (utils.py is filtered out as IDENTICAL)
        self.assertEqual(len(self.app.tree.get_children()), 2)

        # Step 4: Clear search
        self.app.search_var.set("")
        self.app._apply_filters()
        self.root.update_idletasks()
        self.assertEqual(len(self.app.tree.get_children()), 4)

        # Step 5: Sort by rel_path
        self.app._sort_column("rel_path")
        self.root.update_idletasks()
        children = self.app.tree.get_children()
        first_path = self.app.tree.item(children[0], "values")[0]
        self.assertEqual(first_path, "config.json")

        # Step 6: Re-enable all filters
        for s in FileStatus:
            self.app._filter_vars[s.value].set(True)
        self.app._apply_filters()
        self.root.update_idletasks()
        self.assertEqual(len(self.app.tree.get_children()), 5)


# ===========================================================================
# Test: DiffViewer colour tags
# ===========================================================================

class TestDiffViewerTags(unittest.TestCase):
    """Tests for DiffViewer text widget colour tags."""

    def setUp(self):
        self.root = _create_tk_root()
        self._tmpdir = tempfile.mkdtemp()
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        path = os.path.join(self._tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_diff_tags_exist(self):
        """DiffViewer text widget should have addition, deletion, header, range tags."""
        left = self._write_file("left.txt", "a\nb\nc\n")
        right = self._write_file("right.txt", "a\nx\nc\n")
        dv = DiffViewer(self.root, left, right, "tags.txt")
        self.root.update_idletasks()

        # Check tags are configured
        for tag_name in ("addition", "deletion", "header", "range"):
            config = dv.text.tag_configure(tag_name)
            self.assertIsNotNone(config, f"Tag '{tag_name}' should be configured")

        dv.destroy()

    def test_diff_has_addition_and_deletion_content(self):
        """DiffViewer should produce text with both + and - lines for changed files."""
        left = self._write_file("left.txt", "line1\nline2\nline3\n")
        right = self._write_file("right.txt", "line1\nchanged\nline3\n")
        dv = DiffViewer(self.root, left, right, "changes.txt")
        self.root.update_idletasks()

        dv.text.configure(state=tk.NORMAL)
        text = dv.text.get("1.0", tk.END)
        dv.text.configure(state=tk.DISABLED)

        self.assertIn("-line2", text)
        self.assertIn("+changed", text)
        dv.destroy()


# ===========================================================================
# Test: Theme Application
# ===========================================================================

class TestTheme(unittest.TestCase):
    """Tests for the _apply_best_theme helper."""

    def setUp(self):
        self.root = _create_tk_root()
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_theme_is_applied(self):
        """The style should have a theme applied (not empty)."""
        style = ttk.Style(self.root)
        from DirCompare.gui import _apply_best_theme
        _apply_best_theme(style)
        current = style.theme_use()
        self.assertIsInstance(current, str)
        self.assertGreater(len(current), 0)


# ===========================================================================
# Test: ComparisonResult dataclass fields
# ===========================================================================

class TestComparisonResultFields(unittest.TestCase):
    """Tests that ComparisonResult has the expected fields including new ones."""

    def test_timestamp_field(self):
        """ComparisonResult should have a timestamp field."""
        r = _make_result(timestamp="2026-01-01 00:00:00")
        self.assertEqual(r.timestamp, "2026-01-01 00:00:00")

    def test_timestamp_default_empty(self):
        """ComparisonResult timestamp should default to empty string."""
        r = ComparisonResult(
            left_dir="", right_dir="",
            left_file_count=0, right_file_count=0,
            left_total_size=0, right_total_size=0,
            left_versions=[], right_versions=[],
            score=0, confidence="Low",
            explanation="", rows=[],
        )
        self.assertEqual(r.timestamp, "")

    def test_file_type_counts_field(self):
        """ComparisonResult should have a file_type_counts field."""
        r = _make_result(file_type_counts={".py": 5, ".js": 3})
        self.assertEqual(r.file_type_counts[".py"], 5)
        self.assertEqual(r.file_type_counts[".js"], 3)

    def test_file_type_counts_default_empty(self):
        """ComparisonResult file_type_counts should default to empty dict."""
        r = ComparisonResult(
            left_dir="", right_dir="",
            left_file_count=0, right_file_count=0,
            left_total_size=0, right_total_size=0,
            left_versions=[], right_versions=[],
            score=0, confidence="Low",
            explanation="", rows=[],
        )
        self.assertEqual(r.file_type_counts, {})

    def test_status_counts_field(self):
        """ComparisonResult should have a status_counts field."""
        r = _make_result(status_counts={"Identical": 5, "Left Only": 2})
        self.assertEqual(r.status_counts["Identical"], 5)

    def test_warnings_field(self):
        """ComparisonResult should have a warnings field."""
        r = _make_result(warnings=["warn1", "warn2"])
        self.assertEqual(len(r.warnings), 2)

    def test_weights_field(self):
        """ComparisonResult should have a weights field."""
        w = ScoringWeights(unique_file=10)
        r = _make_result(weights=w)
        self.assertEqual(r.weights.unique_file, 10)


# ===========================================================================
# Test: Keyboard Bindings
# ===========================================================================

class TestKeyboardBindings(unittest.TestCase):
    """Tests that keyboard shortcuts are bound."""

    def setUp(self):
        self.root = _create_tk_root()
        self.app = DirCompareApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_f5_bound(self):
        """F5 should be bound to the root window."""
        bindings = self.root.bind()
        # Tk reports bindings like '<F5>', '<Key-F5>', etc.
        has_f5 = any("F5" in b for b in bindings)
        self.assertTrue(has_f5, f"F5 binding not found in {bindings}")

    def test_ctrl_return_bound(self):
        """Ctrl+Return should be bound."""
        bindings = self.root.bind()
        has_ctrl_return = any("Control" in b and "Return" in b for b in bindings)
        self.assertTrue(has_ctrl_return, f"Ctrl+Return binding not found in {bindings}")

    def test_escape_bound(self):
        """Escape should be bound."""
        bindings = self.root.bind()
        has_esc = any("Escape" in b for b in bindings)
        self.assertTrue(has_esc, f"Escape binding not found in {bindings}")

    def test_ctrl_f_bound(self):
        """Ctrl+F should be bound for search focus."""
        bindings = self.root.bind()
        has_ctrl_f = any("Control" in b and ("f" in b or "F" in b) for b in bindings)
        self.assertTrue(has_ctrl_f, f"Ctrl+F binding not found in {bindings}")

    def test_ctrl_s_bound(self):
        """Ctrl+S should be bound for swap."""
        bindings = self.root.bind()
        has_ctrl_s = any("Control" in b and ("s" in b or "S" in b) for b in bindings)
        self.assertTrue(has_ctrl_s, f"Ctrl+S binding not found in {bindings}")


# ===========================================================================
# SettingsDialog cache checkbox tests
# ===========================================================================

class TestSettingsDialogCache(unittest.TestCase):
    """Tests for the cache checkbox in SettingsDialog."""

    def setUp(self):
        self.root = _create_tk_root()
        # Patch wait_window to prevent blocking
        self._orig_wait = tk.Toplevel.wait_window
        tk.Toplevel.wait_window = lambda self, w=None: None

    def tearDown(self):
        tk.Toplevel.wait_window = self._orig_wait
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_cache_checkbox_exists(self):
        """SettingsDialog has a _cache_var attribute (BooleanVar)."""
        dlg = SettingsDialog(self.root, ScoringWeights(), "md5", False)
        self.assertIsInstance(dlg._cache_var, tk.BooleanVar)
        dlg.destroy()

    def test_cache_default_off(self):
        """Cache checkbox defaults to unchecked."""
        dlg = SettingsDialog(self.root, ScoringWeights(), "md5", False)
        self.assertFalse(dlg._cache_var.get())
        dlg.destroy()

    def test_cache_default_on_when_passed(self):
        """Cache checkbox is checked when current_use_cache=True."""
        dlg = SettingsDialog(self.root, ScoringWeights(), "md5", True)
        self.assertTrue(dlg._cache_var.get())
        dlg.destroy()

    def test_ok_sets_cache_result(self):
        """Clicking OK populates cache_result."""
        dlg = SettingsDialog(self.root, ScoringWeights(), "md5", False)
        dlg._cache_var.set(True)
        dlg._ok()
        self.assertTrue(dlg.cache_result)

    def test_cache_result_none_on_cancel(self):
        """Clicking Cancel leaves cache_result as None."""
        dlg = SettingsDialog(self.root, ScoringWeights(), "md5", True)
        dlg._cancel()
        self.assertIsNone(dlg.cache_result)

    def test_reset_clears_cache(self):
        """Reset defaults sets cache to False."""
        dlg = SettingsDialog(self.root, ScoringWeights(), "md5", True)
        self.assertTrue(dlg._cache_var.get())
        dlg._reset()
        self.assertFalse(dlg._cache_var.get())
        dlg.destroy()


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    unittest.main()
