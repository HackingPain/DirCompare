"""
DirCompare GUI
Full-featured tkinter interface for comparing two directories.
Uses only Python standard library.
"""

import difflib
import json as _json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .engine import (
    ComparisonResult,
    ComparisonRow,
    DEFAULT_IGNORE_PATTERNS,
    FileStatus,
    IGNORE_CATEGORIES,
    ScoringWeights,
    compare_directories,
    export_report_csv,
    export_report_html,
    export_report_json,
    export_report_txt,
    fmt_size,
)


# ---------------------------------------------------------------------------
# Theme helper
# ---------------------------------------------------------------------------

def _apply_best_theme(style: ttk.Style):
    """Apply the best available ttk theme in preference order."""
    available = style.theme_names()
    for theme in ("clam", "vista", "winnative", "default"):
        if theme in available:
            style.theme_use(theme)
            return


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------

def _get_config_path() -> str:
    """Get path to the config file for persisting settings."""
    home = os.path.expanduser("~")
    return os.path.join(home, ".dircompare_config.json")

def _load_config() -> dict:
    try:
        with open(_get_config_path(), "r") as f:
            return _json.load(f)
    except (OSError, ValueError):
        return {}

def _save_config(data: dict):
    try:
        with open(_get_config_path(), "w") as f:
            _json.dump(data, f, indent=2)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Diff Viewer
# ---------------------------------------------------------------------------

class DiffViewer(tk.Toplevel):
    """Toplevel window showing a unified diff between two text files."""

    def __init__(self, parent, left_path: str, right_path: str, rel_path: str):
        super().__init__(parent)
        self.title(f"Diff: {rel_path}")
        self.geometry("850x600")
        self.minsize(500, 300)
        self.transient(parent)

        frame = ttk.Frame(self, padding=4)
        frame.pack(fill=tk.BOTH, expand=True)

        # Toolbar with view mode toggle
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        self._view_mode = tk.StringVar(value="unified")
        ttk.Radiobutton(toolbar, text="Unified", variable=self._view_mode,
                        value="unified", command=self._refresh_diff).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(toolbar, text="Side by Side", variable=self._view_mode,
                        value="sidebyside", command=self._refresh_diff).pack(side=tk.LEFT, padx=4)

        self._left_path = left_path
        self._right_path = right_path
        self._rel_path = rel_path

        # Unified view
        self.text = tk.Text(frame, wrap=tk.NONE, font=("Consolas", 10))
        ysb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.text.yview)
        xsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.text.xview)
        self.text.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)

        self.text.grid(row=1, column=0, sticky="nsew")
        ysb.grid(row=1, column=1, sticky="ns")
        xsb.grid(row=2, column=0, sticky="ew")
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        # Side-by-side view (hidden initially)
        self._sbs_frame = ttk.Frame(frame)
        self._left_text = tk.Text(self._sbs_frame, wrap=tk.NONE, font=("Consolas", 10), width=40)
        self._right_text = tk.Text(self._sbs_frame, wrap=tk.NONE, font=("Consolas", 10), width=40)

        # Synchronized scrolling
        sbs_ysb = ttk.Scrollbar(self._sbs_frame, orient=tk.VERTICAL)
        sbs_ysb.configure(command=lambda *a: (self._left_text.yview(*a), self._right_text.yview(*a)))
        self._left_text.configure(yscrollcommand=lambda *a: sbs_ysb.set(*a))
        self._right_text.configure(yscrollcommand=lambda *a: sbs_ysb.set(*a))

        self._left_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._right_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sbs_ysb.pack(side=tk.RIGHT, fill=tk.Y)

        # Configure tags for all text widgets
        for tw in (self.text, self._left_text, self._right_text):
            tw.tag_configure("addition", background="#d4edda")
            tw.tag_configure("deletion", background="#f8d7da")
            tw.tag_configure("header", background="#cce5ff")
            tw.tag_configure("range", background="#e2d5f1")
            tw.tag_configure("unchanged", background="#ffffff")

        self._load_diff(left_path, right_path, rel_path)
        self.text.configure(state=tk.DISABLED)

    # ---- internal --------------------------------------------------------

    def _load_diff(self, left_path: str, right_path: str, rel_path: str):
        left_exists = left_path and os.path.isfile(left_path)
        right_exists = right_path and os.path.isfile(right_path)

        if not left_exists and not right_exists:
            self.text.insert(tk.END, "Neither file exists on disk.")
            return

        if not left_exists:
            self.text.insert(tk.END, f"File only exists on the right side:\n{right_path}")
            return

        if not right_exists:
            self.text.insert(tk.END, f"File only exists on the left side:\n{left_path}")
            return

        # Check for binary content
        if self._is_binary(left_path) or self._is_binary(right_path):
            self.text.insert(tk.END, "Binary file -- diff not available.\n\n")
            self.text.insert(tk.END, f"Left:  {left_path}\n")
            self.text.insert(tk.END, f"Right: {right_path}\n")
            return

        try:
            with open(left_path, "r", encoding="utf-8", errors="replace") as f:
                left_lines = f.readlines()
            with open(right_path, "r", encoding="utf-8", errors="replace") as f:
                right_lines = f.readlines()
        except OSError as exc:
            self.text.insert(tk.END, f"Error reading files: {exc}")
            return

        diff = difflib.unified_diff(
            left_lines,
            right_lines,
            fromfile=f"left/{rel_path}",
            tofile=f"right/{rel_path}",
            lineterm="",
        )

        any_output = False
        for line in diff:
            any_output = True
            clean = line.rstrip("\n\r")
            if clean.startswith("+++") or clean.startswith("---"):
                tag = "header"
            elif clean.startswith("@@"):
                tag = "range"
            elif clean.startswith("+"):
                tag = "addition"
            elif clean.startswith("-"):
                tag = "deletion"
            else:
                tag = ""

            if tag:
                self.text.insert(tk.END, clean + "\n", tag)
            else:
                self.text.insert(tk.END, clean + "\n")

        if not any_output:
            self.text.insert(tk.END, "Files are identical.")

    @staticmethod
    def _is_binary(path: str) -> bool:
        try:
            with open(path, "rb") as f:
                chunk = f.read(8192)
            return b"\x00" in chunk
        except OSError:
            return True

    def _refresh_diff(self):
        mode = self._view_mode.get()
        if mode == "unified":
            self._sbs_frame.grid_forget()
            self.text.grid(row=1, column=0, sticky="nsew")
            # Reload unified
            self.text.configure(state=tk.NORMAL)
            self.text.delete("1.0", tk.END)
            self._load_diff(self._left_path, self._right_path, self._rel_path)
            self.text.configure(state=tk.DISABLED)
        else:
            self.text.grid_forget()
            self._sbs_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
            self._load_side_by_side()

    def _load_side_by_side(self):
        self._left_text.configure(state=tk.NORMAL)
        self._right_text.configure(state=tk.NORMAL)
        self._left_text.delete("1.0", tk.END)
        self._right_text.delete("1.0", tk.END)

        left_exists = self._left_path and os.path.isfile(self._left_path)
        right_exists = self._right_path and os.path.isfile(self._right_path)

        if not left_exists or not right_exists or self._is_binary(self._left_path or "") or self._is_binary(self._right_path or ""):
            self._left_text.insert(tk.END, "Side-by-side view not available for binary or missing files.")
            self._left_text.configure(state=tk.DISABLED)
            self._right_text.configure(state=tk.DISABLED)
            return

        try:
            with open(self._left_path, "r", encoding="utf-8", errors="replace") as f:
                left_lines = f.readlines()
            with open(self._right_path, "r", encoding="utf-8", errors="replace") as f:
                right_lines = f.readlines()
        except OSError:
            self._left_text.insert(tk.END, "Error reading files.")
            self._left_text.configure(state=tk.DISABLED)
            self._right_text.configure(state=tk.DISABLED)
            return

        matcher = difflib.SequenceMatcher(None, left_lines, right_lines)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for line in left_lines[i1:i2]:
                    self._left_text.insert(tk.END, line, "unchanged")
                for line in right_lines[j1:j2]:
                    self._right_text.insert(tk.END, line, "unchanged")
            elif tag == "delete":
                for line in left_lines[i1:i2]:
                    self._left_text.insert(tk.END, line, "deletion")
                # Add blank lines on right to keep alignment
                for _ in range(i2 - i1):
                    self._right_text.insert(tk.END, "\n")
            elif tag == "insert":
                for _ in range(j2 - j1):
                    self._left_text.insert(tk.END, "\n")
                for line in right_lines[j1:j2]:
                    self._right_text.insert(tk.END, line, "addition")
            elif tag == "replace":
                for line in left_lines[i1:i2]:
                    self._left_text.insert(tk.END, line, "deletion")
                for line in right_lines[j1:j2]:
                    self._right_text.insert(tk.END, line, "addition")
                # Pad shorter side
                diff = (i2 - i1) - (j2 - j1)
                if diff > 0:
                    for _ in range(diff):
                        self._right_text.insert(tk.END, "\n")
                elif diff < 0:
                    for _ in range(-diff):
                        self._left_text.insert(tk.END, "\n")

        self._left_text.configure(state=tk.DISABLED)
        self._right_text.configure(state=tk.DISABLED)


# ---------------------------------------------------------------------------
# Settings Dialog
# ---------------------------------------------------------------------------

class SettingsDialog(tk.Toplevel):
    """Modal dialog for configuring scoring weights."""

    def __init__(self, parent, current_weights: ScoringWeights, current_hash_algorithm: str = "md5", current_use_cache: bool = False):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("420x500")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result: ScoringWeights | None = None
        self.hash_result: str | None = None
        self.cache_result: bool | None = None
        self._defaults = ScoringWeights()

        body = ttk.Frame(self, padding=16)
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(body, text="Scoring Weights", font=("", 11, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 10), sticky="w"
        )

        labels = [
            ("Unique file:", "unique_file"),
            ("Content analysis:", "content_analysis"),
            ("Version string:", "version_string"),
            ("Git commits:", "git_commits"),
        ]

        self._vars: dict[str, tk.IntVar] = {}
        for idx, (label_text, attr) in enumerate(labels, start=1):
            ttk.Label(body, text=label_text).grid(row=idx, column=0, sticky="w", padx=(0, 12), pady=3)
            var = tk.IntVar(value=getattr(current_weights, attr))
            self._vars[attr] = var
            sb = ttk.Spinbox(body, from_=0, to=20, textvariable=var, width=6)
            sb.grid(row=idx, column=1, sticky="w", pady=3)

        hash_row = len(labels) + 1
        ttk.Separator(body, orient=tk.HORIZONTAL).grid(
            row=hash_row, column=0, columnspan=2, sticky="ew", pady=(12, 8)
        )
        ttk.Label(body, text="Hash Algorithm", font=("", 11, "bold")).grid(
            row=hash_row + 1, column=0, columnspan=2, pady=(0, 6), sticky="w"
        )
        self._hash_var = tk.StringVar(value=current_hash_algorithm)
        hash_frame = ttk.Frame(body)
        hash_frame.grid(row=hash_row + 2, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(hash_frame, text="MD5 (faster)", variable=self._hash_var, value="md5").pack(side=tk.LEFT, padx=(0, 16))
        ttk.Radiobutton(hash_frame, text="SHA-256 (more secure)", variable=self._hash_var, value="sha256").pack(side=tk.LEFT)

        cache_sep_row = len(labels) + 4
        ttk.Separator(body, orient=tk.HORIZONTAL).grid(
            row=cache_sep_row, column=0, columnspan=2, sticky="ew", pady=(12, 8)
        )
        ttk.Label(body, text="Performance", font=("", 11, "bold")).grid(
            row=cache_sep_row + 1, column=0, columnspan=2, pady=(0, 6), sticky="w"
        )
        self._cache_var = tk.BooleanVar(value=current_use_cache)
        ttk.Checkbutton(
            body, text="Cache file hashes (speeds up repeated comparisons)",
            variable=self._cache_var,
        ).grid(row=cache_sep_row + 2, column=0, columnspan=2, sticky="w")

        note_row = cache_sep_row + 3
        note = ttk.Label(
            body,
            text=(
                "Note: Content volume heuristic ('more content = newer')\n"
                "may not be accurate for refactored code."
            ),
            foreground="gray",
            wraplength=380,
            justify=tk.LEFT,
        )
        note.grid(row=note_row, column=0, columnspan=2, pady=(12, 8), sticky="w")

        # Buttons
        btn_frame = ttk.Frame(body)
        btn_frame.grid(row=note_row + 1, column=0, columnspan=2, pady=(10, 0), sticky="e")

        ttk.Button(btn_frame, text="Reset Defaults", command=self._reset).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.LEFT)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.focus_set()
        self.wait_window(self)

    def _ok(self):
        self.result = ScoringWeights(
            unique_file=self._vars["unique_file"].get(),
            content_analysis=self._vars["content_analysis"].get(),
            version_string=self._vars["version_string"].get(),
            git_commits=self._vars["git_commits"].get(),
        )
        self.hash_result = self._hash_var.get()
        self.cache_result = self._cache_var.get()
        self.grab_release()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()

    def _reset(self):
        for attr, var in self._vars.items():
            var.set(getattr(self._defaults, attr))
        self._cache_var.set(False)


# ---------------------------------------------------------------------------
# Ignore Patterns Dialog
# ---------------------------------------------------------------------------

class IgnorePatternsDialog(tk.Toplevel):
    """Dialog for editing ignore patterns with category presets."""

    CATEGORIES = IGNORE_CATEGORIES

    def __init__(self, parent, current_patterns: str):
        super().__init__(parent)
        self.title("Ignore Patterns Editor")
        self.geometry("700x550")
        self.minsize(500, 400)
        self.transient(parent)
        self.grab_set()

        self.result: str | None = None

        body = ttk.Frame(self, padding=12)
        body.pack(fill=tk.BOTH, expand=True)

        # Category checkboxes
        cat_frame = ttk.LabelFrame(body, text="Quick Add Categories", padding=6)
        cat_frame.pack(fill=tk.X, pady=(0, 8))

        self._cat_vars: dict[str, tk.BooleanVar] = {}
        cat_inner = ttk.Frame(cat_frame)
        cat_inner.pack(fill=tk.X)

        current_set = {p.strip() for p in current_patterns.split(",") if p.strip()}

        for idx, (name, patterns_str) in enumerate(self.CATEGORIES.items()):
            cat_patterns = {p.strip() for p in patterns_str.split(",") if p.strip()}
            # Check if all patterns in this category are currently active
            is_active = cat_patterns.issubset(current_set)
            var = tk.BooleanVar(value=is_active)
            self._cat_vars[name] = var
            cb = ttk.Checkbutton(cat_inner, text=name, variable=var,
                                command=self._on_category_toggle)
            row, col = divmod(idx, 4)
            cb.grid(row=row, column=col, sticky="w", padx=4, pady=1)

        # Text area
        ttk.Label(body, text="Patterns (one per line or comma-separated):").pack(anchor="w", pady=(4, 2))

        text_frame = ttk.Frame(body)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.text = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 10))
        ysb = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=ysb.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ysb.pack(side=tk.RIGHT, fill=tk.Y)

        # Load current patterns - one per line
        patterns_list = [p.strip() for p in current_patterns.split(",") if p.strip()]
        self.text.insert("1.0", "\n".join(patterns_list))

        # Buttons
        btn_frame = ttk.Frame(body)
        btn_frame.pack(fill=tk.X, pady=(8, 0))

        ttk.Button(btn_frame, text="Select All", command=self._select_all_cats).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Clear All", command=self._clear_all_cats).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(btn_frame, text="Cancel", command=self._cancel).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.RIGHT)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.focus_set()
        self.wait_window(self)

    def _on_category_toggle(self):
        """Rebuild text area based on checked categories."""
        # Get manually entered patterns (not in any category)
        current_text = self.text.get("1.0", tk.END).strip()
        current_patterns = {p.strip() for p in current_text.replace("\n", ",").split(",") if p.strip()}

        all_cat_patterns = set()
        for patterns_str in self.CATEGORIES.values():
            for p in patterns_str.split(","):
                all_cat_patterns.add(p.strip())

        # Keep patterns not belonging to any category
        custom_patterns = current_patterns - all_cat_patterns

        # Add patterns from checked categories
        new_patterns = set(custom_patterns)
        for name, var in self._cat_vars.items():
            if var.get():
                for p in self.CATEGORIES[name].split(","):
                    p = p.strip()
                    if p:
                        new_patterns.add(p)

        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", "\n".join(sorted(new_patterns)))

    def _select_all_cats(self):
        for var in self._cat_vars.values():
            var.set(True)
        self._on_category_toggle()

    def _clear_all_cats(self):
        for var in self._cat_vars.values():
            var.set(False)
        self._on_category_toggle()

    def _ok(self):
        text = self.text.get("1.0", tk.END).strip()
        # Convert newlines to comma-separated
        patterns = [p.strip() for p in text.replace("\n", ",").split(",") if p.strip()]
        self.result = ", ".join(patterns)
        self.grab_release()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------

class DirCompareApp:
    """The main DirCompare GUI application."""

    # Row tags: maps FileStatus value to (tag_name, background_colour)
    STATUS_TAGS = {
        FileStatus.LEFT_ONLY.value: ("left_only", "#ffffcc"),
        FileStatus.RIGHT_ONLY.value: ("right_only", "#cce5ff"),
        FileStatus.IDENTICAL.value: ("identical", "#d4edda"),
        FileStatus.LEFT_NEWER.value: ("left_newer", "#ffe0b2"),
        FileStatus.RIGHT_NEWER.value: ("right_newer", "#b3e5fc"),
        FileStatus.UNKNOWN.value: ("unknown", "#e0e0e0"),
    }

    DEFAULT_IGNORE = ", ".join(DEFAULT_IGNORE_PATTERNS)
    MAX_DISPLAY_ROWS = 5000

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DirCompare")
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)

        self.style = ttk.Style(root)
        _apply_best_theme(self.style)

        # State
        self.left_var = tk.StringVar()
        self.right_var = tk.StringVar()
        self.ignore_var = tk.StringVar(value=self.DEFAULT_IGNORE)
        self.use_gitignore_var = tk.BooleanVar(value=False)
        self.search_var = tk.StringVar()
        self._search_after_id = None
        self.search_var.trace_add("write", lambda *_: self._schedule_search())

        self.weights = ScoringWeights()
        self.hash_algorithm = "md5"
        self.use_cache = False
        self.result: ComparisonResult | None = None
        self.all_rows: list[ComparisonRow] = []
        self._cancel_event = threading.Event()
        self._comparing = False
        self._sort_reverse: dict[str, bool] = {}
        self._compare_start_time: float = 0.0

        # Filter checkbox vars  -- {FileStatus.value: BooleanVar}
        self._filter_vars: dict[str, tk.BooleanVar] = {}
        self._filter_cbs: dict[str, ttk.Checkbutton] = {}

        # Lazy loading pagination
        self._display_all = False

        # Export filtered option
        self._export_filtered_var = tk.BooleanVar(value=False)

        # Load remembered directories
        config = _load_config()
        if config.get("left_dir"):
            self.left_var.set(config["left_dir"])
        if config.get("right_dir"):
            self.right_var.set(config["right_dir"])
        if config.get("hash_algorithm"):
            self.hash_algorithm = config["hash_algorithm"]
        if config.get("use_cache"):
            self.use_cache = config["use_cache"]

        self._build_ui()
        self._bind_keys()

        # Set application icon
        try:
            from .icon import get_icon_photo
            self._icon = get_icon_photo(self.root)
            self.root.iconphoto(True, self._icon)
        except Exception:
            pass  # Icon is non-critical

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        pad = dict(padx=6, pady=3)

        # ---- Menu bar ----
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        history_menu = tk.Menu(menubar, tearoff=0)
        history_menu.add_command(label="View History", command=self._show_history)
        history_menu.add_command(label="Clear History", command=self._clear_history)
        menubar.add_cascade(label="History", menu=history_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Keyboard Shortcuts", command=self._show_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label="About DirCompare", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        # ---- directory pickers ------------------------------------------
        dir_frame = ttk.LabelFrame(self.root, text="Directories", padding=8)
        dir_frame.pack(fill=tk.X, **pad)

        # Left directory
        ttk.Label(dir_frame, text="Left:").grid(row=0, column=0, sticky="w")
        self.left_entry = ttk.Entry(dir_frame, textvariable=self.left_var)
        self.left_entry.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(dir_frame, text="Browse...", command=lambda: self._browse(self.left_var)).grid(row=0, column=2)

        # Swap button
        ttk.Button(dir_frame, text="\u21c4", width=3, command=self._swap_dirs).grid(
            row=0, column=3, rowspan=2, padx=8
        )

        # Right directory
        ttk.Label(dir_frame, text="Right:").grid(row=1, column=0, sticky="w")
        self.right_entry = ttk.Entry(dir_frame, textvariable=self.right_var)
        self.right_entry.grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Button(dir_frame, text="Browse...", command=lambda: self._browse(self.right_var)).grid(row=1, column=2)

        dir_frame.columnconfigure(1, weight=1)

        # ---- ignore patterns -------------------------------------------
        ign_frame = ttk.Frame(dir_frame)
        ign_frame.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(6, 0))

        ttk.Label(ign_frame, text="Ignore patterns:").pack(side=tk.LEFT)
        self.ignore_summary_label = ttk.Label(ign_frame, text=self._ignore_summary(), foreground="gray")
        self.ignore_summary_label.pack(side=tk.LEFT, padx=4)
        ttk.Button(ign_frame, text="Edit...", command=self._open_ignore_editor).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(ign_frame, text="Use .gitignore", variable=self.use_gitignore_var).pack(side=tk.LEFT, padx=(4, 0))

        # ---- action buttons --------------------------------------------
        btn_frame = ttk.Frame(self.root, padding=4)
        btn_frame.pack(fill=tk.X, **pad)

        self.compare_btn = ttk.Button(btn_frame, text="Compare", command=self._start_compare)
        self.compare_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.cancel_btn = ttk.Button(btn_frame, text="Cancel", command=self._cancel_compare, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.export_btn = ttk.Button(btn_frame, text="Export Report", command=self._export, state=tk.DISABLED)
        self.export_btn.pack(side=tk.LEFT, padx=(0, 4))

        ttk.Checkbutton(btn_frame, text="Filtered only", variable=self._export_filtered_var).pack(side=tk.LEFT, padx=(0, 4))

        self.recompare_btn = ttk.Button(btn_frame, text="Re-compare", command=self._recompare, state=tk.DISABLED)
        self.recompare_btn.pack(side=tk.LEFT, padx=(0, 4))

        ttk.Button(btn_frame, text="\u2699 Settings", command=self._open_settings).pack(side=tk.LEFT)

        # ---- progress ---------------------------------------------------
        prog_frame = ttk.Frame(self.root, padding=4)
        prog_frame.pack(fill=tk.X, **pad)

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(prog_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.status_label = ttk.Label(prog_frame, text="Ready", width=18, anchor="e")
        self.status_label.pack(side=tk.LEFT, padx=(6, 0))

        # ---- summary panel ----------------------------------------------
        summary_header = ttk.Frame(self.root)
        summary_header.pack(fill=tk.X, padx=6, pady=(3, 0))
        ttk.Label(summary_header, text="Summary", font=("", 9, "bold")).pack(side=tk.LEFT)
        self.copy_summary_btn = ttk.Button(summary_header, text="Copy", width=6, command=self._copy_summary)
        self.copy_summary_btn.pack(side=tk.RIGHT)

        summary_frame = ttk.Frame(self.root, padding=4)
        summary_frame.pack(fill=tk.X, padx=6, pady=(0, 3))

        self.summary_text = tk.Text(summary_frame, height=6, wrap=tk.WORD, font=("Consolas", 10))
        self.summary_text.pack(fill=tk.X)
        self.summary_text.configure(state=tk.DISABLED)

        # Summary colour tags
        self.summary_text.tag_configure("verdict_high", foreground="green")
        self.summary_text.tag_configure("verdict_medium", foreground="orange")
        self.summary_text.tag_configure("verdict_low", foreground="gray")
        self.summary_text.tag_configure("warning", foreground="orange", font=("Consolas", 10, "italic"))

        # ---- filter checkboxes ------------------------------------------
        filter_frame = ttk.Frame(self.root, padding=4)
        filter_frame.pack(fill=tk.X, **pad)

        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=(0, 4))

        for status in FileStatus:
            var = tk.BooleanVar(value=True)
            self._filter_vars[status.value] = var
            cb = ttk.Checkbutton(
                filter_frame,
                text=status.value,
                variable=var,
                command=self._apply_filters,
            )
            cb.pack(side=tk.LEFT, padx=4)
            self._filter_cbs[status.value] = cb

        # ---- search box -------------------------------------------------
        search_frame = ttk.Frame(self.root, padding=4)
        search_frame.pack(fill=tk.X, **pad)

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 4))
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.showing_label = ttk.Label(search_frame, text="")
        self.showing_label.pack(side=tk.LEFT)
        self.showing_label.bind("<Button-1>", self._on_showing_label_click)
        self.showing_label.configure(cursor="hand2")

        # ---- treeview table ---------------------------------------------
        tree_frame = ttk.Frame(self.root, padding=4)
        tree_frame.pack(fill=tk.BOTH, expand=True, **pad)

        columns = ("rel_path", "status", "size_left", "size_right", "notes")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")

        for col in columns:
            self.tree.heading(col, text=col.replace("_", " ").title(),
                              command=lambda c=col: self._sort_column(c))

        self.tree.column("rel_path", width=350, minwidth=150)
        self.tree.column("status", width=100, minwidth=80, anchor="center")
        self.tree.column("size_left", width=100, minwidth=70, anchor="e")
        self.tree.column("size_right", width=100, minwidth=70, anchor="e")
        self.tree.column("notes", width=350, minwidth=100)

        ysb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        xsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # Row tags for colour coding
        for status_value, (tag, bg) in self.STATUS_TAGS.items():
            self.tree.tag_configure(tag, background=bg)

        # Double-click opens diff
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Return>", self._on_double_click)

        # Tooltip on hover
        self._tooltip = None
        self._tooltip_id = None
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", self._hide_tooltip)

        # Placeholder text for directory entries
        self._add_placeholder(self.left_entry, self.left_var, "Drop or browse for left directory...")
        self._add_placeholder(self.right_entry, self.right_var, "Drop or browse for right directory...")

    # ------------------------------------------------------------------ keys
    def _bind_keys(self):
        self.root.bind("<F5>", lambda e: self._start_compare())
        self.root.bind("<Control-Return>", lambda e: self._start_compare())
        self.root.bind("<Escape>", lambda e: self._cancel_compare())
        self.root.bind("<Control-e>", lambda e: self._export())
        self.root.bind("<Control-E>", lambda e: self._export())
        self.root.bind("<Control-s>", lambda e: self._swap_dirs())
        self.root.bind("<Control-S>", lambda e: self._swap_dirs())
        self.root.bind("<Control-f>", lambda e: self.search_entry.focus_set())
        self.root.bind("<Control-F>", lambda e: self.search_entry.focus_set())
        self.root.bind("<Shift-F5>", lambda e: self._recompare())
        self.root.bind("<F1>", lambda e: self._show_about())

    # ------------------------------------------------------------------ browse / swap
    def _browse(self, var: tk.StringVar):
        path = filedialog.askdirectory(title="Select Directory")
        if path:
            var.set(path)
            # Clear placeholder styling if entry exists
            for entry, v in [(self.left_entry, self.left_var), (self.right_entry, self.right_var)]:
                if v is var:
                    entry.configure(foreground="")

    def _swap_dirs(self):
        left = self.left_var.get()
        right = self.right_var.get()
        self.left_var.set(right)
        self.right_var.set(left)

    # ------------------------------------------------------------------ compare
    def _start_compare(self):
        left = self.left_var.get().strip()
        right = self.right_var.get().strip()
        # Ignore placeholder text
        if left.startswith("Drop or browse"):
            left = ""
        if right.startswith("Drop or browse"):
            right = ""

        if not left or not right:
            messagebox.showwarning("DirCompare", "Please select both directories.")
            return
        if not os.path.isdir(left):
            messagebox.showerror("DirCompare", f"Left directory does not exist:\n{left}")
            return
        if not os.path.isdir(right):
            messagebox.showerror("DirCompare", f"Right directory does not exist:\n{right}")
            return
        if self._comparing:
            return

        self._comparing = True
        self._cancel_event.clear()
        self._compare_start_time = time.monotonic()
        self.compare_btn.configure(state=tk.DISABLED)
        self.cancel_btn.configure(state=tk.NORMAL)
        self.export_btn.configure(state=tk.DISABLED)
        self.progress_var.set(0)
        self.status_label.configure(text="0%")

        raw_patterns = [p.strip() for p in self.ignore_var.get().split(",") if p.strip()]

        thread = threading.Thread(
            target=self._compare_worker,
            args=(left, right, raw_patterns, self.use_gitignore_var.get(), ScoringWeights(
                unique_file=self.weights.unique_file,
                content_analysis=self.weights.content_analysis,
                version_string=self.weights.version_string,
                git_commits=self.weights.git_commits,
            ), self.hash_algorithm, self.use_cache),
            daemon=True,
        )
        thread.start()

    def _compare_worker(self, left, right, patterns, use_gitignore, weights, hash_algorithm="md5", use_cache=False):
        def progress_cb(fraction, message=""):
            if message:
                stage = message
            elif fraction < 0.45:
                stage = "Scanning left..."
            elif fraction < 0.90:
                stage = "Scanning right..."
            else:
                stage = "Analyzing..."
            self.root.after(0, self._update_progress, fraction, stage)

        try:
            result = compare_directories(
                left_dir=left,
                right_dir=right,
                ignore_patterns=patterns,
                weights=weights,
                use_gitignore=use_gitignore,
                progress_callback=progress_cb,
                cancel_event=self._cancel_event,
                hash_algorithm=hash_algorithm,
                use_cache=use_cache,
            )
            self.root.after(0, self._on_compare_done, result)
        except Exception as exc:
            self.root.after(0, self._on_compare_error, str(exc))

    def _update_progress(self, fraction: float, stage: str = ""):
        pct = min(fraction * 100, 100)
        self.progress_var.set(pct)
        if stage:
            self.status_label.configure(text=f"{pct:.0f}% {stage}")
        else:
            self.status_label.configure(text=f"{pct:.0f}%")

    def _on_compare_done(self, result: ComparisonResult):
        self._comparing = False
        self.compare_btn.configure(state=tk.NORMAL)
        self.cancel_btn.configure(state=tk.DISABLED)
        self.export_btn.configure(state=tk.NORMAL)
        self.recompare_btn.configure(state=tk.NORMAL)
        self.progress_var.set(100)

        elapsed = time.monotonic() - self._compare_start_time
        self.status_label.configure(text=f"Done in {elapsed:.1f}s")

        self.result = result
        self.all_rows = list(result.rows)

        # Update window title with verdict (#7)
        if result.score < 0:
            side = "LEFT"
        elif result.score > 0:
            side = "RIGHT"
        else:
            side = "EQUIVALENT"
        self.root.title(f"DirCompare \u2014 {side} is newer ({result.confidence})" if result.score != 0
                        else f"DirCompare \u2014 Equivalent ({result.confidence})")

        # Remember directories for next session
        _save_config({
            "left_dir": result.left_dir,
            "right_dir": result.right_dir,
            "hash_algorithm": self.hash_algorithm,
            "use_cache": self.use_cache,
        })

        # Save to history
        try:
            from .history import HistoryManager
            HistoryManager().save_entry(HistoryManager.make_entry(result))
        except Exception:
            pass

        self._update_summary(result)
        self._update_column_headings(result)
        self._update_filter_labels(result)
        self._display_all = False
        self._apply_filters()

    def _on_compare_error(self, msg: str):
        self._comparing = False
        self.compare_btn.configure(state=tk.NORMAL)
        self.cancel_btn.configure(state=tk.DISABLED)
        self.progress_var.set(0)
        self.status_label.configure(text="Error")
        messagebox.showerror("DirCompare", f"Comparison failed:\n{msg}")

    def _cancel_compare(self):
        if self._comparing:
            self._cancel_event.set()
            self.status_label.configure(text="Cancelling...")

    # ------------------------------------------------------------------ summary
    def _update_summary(self, result: ComparisonResult):
        self.summary_text.configure(state=tk.NORMAL)
        self.summary_text.delete("1.0", tk.END)

        left_base = os.path.basename(result.left_dir) or result.left_dir
        right_base = os.path.basename(result.right_dir) or result.right_dir

        self.summary_text.insert(tk.END, f"Left:  {result.left_dir}  ({result.left_file_count} files, {fmt_size(result.left_total_size)})\n")
        self.summary_text.insert(tk.END, f"Right: {result.right_dir}  ({result.right_file_count} files, {fmt_size(result.right_total_size)})\n\n")

        # Verdict line -- colour-coded
        if result.score < 0:
            verdict = f"VERDICT: LEFT ({left_base}) is more up to date"
        elif result.score > 0:
            verdict = f"VERDICT: RIGHT ({right_base}) is more up to date"
        else:
            verdict = "VERDICT: Both directories appear equivalent"

        verdict_line = f"{verdict}  (score: {result.score}, confidence: {result.confidence})\n"
        tag_map = {"High": "verdict_high", "Medium": "verdict_medium", "Low": "verdict_low"}
        verdict_tag = tag_map.get(result.confidence, "verdict_low")
        self.summary_text.insert(tk.END, verdict_line, verdict_tag)

        self.summary_text.insert(tk.END, f"Explanation: {result.explanation}\n")

        if hasattr(result, 'score_breakdown') and result.score_breakdown:
            parts = [f"{k.replace('_', ' ')}={v:+d}" for k, v in result.score_breakdown.items()]
            self.summary_text.insert(tk.END, f"Score breakdown: {', '.join(parts)}\n")

        if hasattr(result, 'file_type_counts') and result.file_type_counts:
            top_types = list(result.file_type_counts.items())[:10]
            ft_str = ", ".join(f"{count} {ext}" for ext, count in top_types)
            self.summary_text.insert(tk.END, f"File types: {ft_str}\n")

        # Warnings
        for w in result.warnings:
            self.summary_text.insert(tk.END, f"WARNING: {w}\n", "warning")

        self.summary_text.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------ column headings
    def _update_column_headings(self, result: ComparisonResult):
        left_base = os.path.basename(result.left_dir) or "Left"
        right_base = os.path.basename(result.right_dir) or "Right"
        self.tree.heading("size_left", text=f"Size ({left_base})")
        self.tree.heading("size_right", text=f"Size ({right_base})")

    # ------------------------------------------------------------------ filter labels
    def _update_filter_labels(self, result: ComparisonResult):
        """Update the filter checkboxes to show counts, e.g. 'Left Only (12)'."""
        counts = result.status_counts  # {FileStatus.value: int}
        for status in FileStatus:
            count = counts.get(status.value, 0)
            label = f"{status.value} ({count})"
            cb = self._filter_cbs[status.value]
            cb.configure(text=label)

    # ------------------------------------------------------------------ filters + search
    def _apply_filters(self):
        """Rebuild the Treeview based on active status filters and search text."""
        self.tree.delete(*self.tree.get_children())
        search_text = self.search_var.get().strip().lower()
        total = len(self.all_rows)
        shown = 0
        truncated = False

        for row in self.all_rows:
            if not self._filter_vars.get(row.status.value, tk.BooleanVar(value=True)).get():
                continue
            if search_text and search_text not in row.rel_path.lower():
                continue

            if not self._display_all and shown >= self.MAX_DISPLAY_ROWS:
                truncated = True
                # Keep counting for the total
                shown += 1
                continue

            sl = fmt_size(row.size_left) if row.size_left is not None else "-"
            sr = fmt_size(row.size_right) if row.size_right is not None else "-"
            tag_info = self.STATUS_TAGS.get(row.status.value)
            tag = (tag_info[0],) if tag_info else ()
            self.tree.insert("", tk.END, values=(row.rel_path, row.status.value, sl, sr, row.notes), tags=tag)
            shown += 1

        if truncated:
            display_count = self.MAX_DISPLAY_ROWS
            self.showing_label.configure(
                text=f"Showing {display_count} of {shown} matched ({total} total) \u2014 click to load all"
            )
        else:
            self.showing_label.configure(text=f"Showing {shown} of {total}")

    # ------------------------------------------------------------------ double-click
    def _on_double_click(self, event):
        sel = self.tree.selection()
        if not sel:
            return

        values = self.tree.item(sel[0], "values")
        if not values:
            return

        rel_path = values[0]

        # Find the matching ComparisonRow
        row = None
        for r in self.all_rows:
            if r.rel_path == rel_path:
                row = r
                break

        if row is None:
            return

        left_path = row.left_path
        right_path = row.right_path

        if not left_path or not right_path:
            side = "left" if left_path else "right"
            messagebox.showinfo(
                "DirCompare",
                f"File only exists on the {side} side.\nCannot show diff.",
            )
            return

        DiffViewer(self.root, left_path, right_path, rel_path)

    # ------------------------------------------------------------------ export
    def _export(self):
        if self.result is None:
            messagebox.showinfo("DirCompare", "No comparison result to export. Run a comparison first.")
            return

        export_result = self.result
        if self._export_filtered_var.get():
            # Build filtered row list
            search_text = self.search_var.get().strip().lower()
            filtered_rows = []
            for row in self.all_rows:
                if not self._filter_vars.get(row.status.value, tk.BooleanVar(value=True)).get():
                    continue
                if search_text and search_text not in row.rel_path.lower():
                    continue
                filtered_rows.append(row)

            # Create a copy with filtered rows
            from dataclasses import replace
            export_result = replace(self.result, rows=filtered_rows)

        path = filedialog.asksaveasfilename(
            title="Export Report",
            defaultextension=".txt",
            filetypes=[
                ("Text files", "*.txt"),
                ("CSV files", "*.csv"),
                ("JSON files", "*.json"),
                ("HTML files", "*.html"),
            ],
        )
        if not path:
            return

        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".csv":
                content = export_report_csv(export_result)
            elif ext == ".json":
                content = export_report_json(export_result)
            elif ext in (".html", ".htm"):
                content = export_report_html(export_result)
            else:
                content = export_report_txt(export_result)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            messagebox.showinfo("DirCompare", f"Report exported to:\n{path}")
        except OSError as exc:
            messagebox.showerror("DirCompare", f"Failed to export report:\n{exc}")

    # ------------------------------------------------------------------ settings
    def _open_settings(self):
        dlg = SettingsDialog(self.root, self.weights, self.hash_algorithm, self.use_cache)
        if dlg.result is not None:
            self.weights = dlg.result
        if dlg.hash_result is not None:
            self.hash_algorithm = dlg.hash_result
        if dlg.cache_result is not None:
            self.use_cache = dlg.cache_result

    # ------------------------------------------------------------------ column sorting (#1)
    def _sort_column(self, col: str):
        """Sort treeview by a column, toggling ascending/descending."""
        reverse = self._sort_reverse.get(col, False)

        # Get all items with their values
        items = [(self.tree.set(child, col), child) for child in self.tree.get_children()]

        # Try numeric sort for size columns
        if col in ("size_left", "size_right"):
            def sort_key(item):
                val = item[0]
                if val == "-":
                    return -1
                # Parse the formatted size back to bytes for sorting
                try:
                    parts = val.split()
                    num = float(parts[0])
                    unit = parts[1] if len(parts) > 1 else "B"
                    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
                    return num * multipliers.get(unit, 1)
                except (ValueError, IndexError):
                    return 0
            items.sort(key=sort_key, reverse=reverse)
        else:
            items.sort(key=lambda x: x[0].lower(), reverse=reverse)

        for idx, (_, child) in enumerate(items):
            self.tree.move(child, "", idx)

        # Toggle direction and update header
        self._sort_reverse[col] = not reverse

        # Update all headers to remove arrows, then add to sorted column
        col_titles = {
            "rel_path": "Relative Path",
            "status": "Status",
            "size_left": "Size Left",
            "size_right": "Size Right",
            "notes": "Notes",
        }
        # Preserve dynamic size column names if result exists
        if self.result:
            left_base = os.path.basename(self.result.left_dir) or "Left"
            right_base = os.path.basename(self.result.right_dir) or "Right"
            col_titles["size_left"] = f"Size ({left_base})"
            col_titles["size_right"] = f"Size ({right_base})"

        for c in ("rel_path", "status", "size_left", "size_right", "notes"):
            title = col_titles.get(c, c)
            self.tree.heading(c, text=title)

        arrow = " \u25b2" if not reverse else " \u25bc"
        current_title = col_titles.get(col, col)
        self.tree.heading(col, text=current_title + arrow)

    # ------------------------------------------------------------------ right-click context menu (#4)
    def _on_right_click(self, event):
        """Show context menu on right-click."""
        item = self.tree.identify_row(event.y)
        if not item:
            return
        self.tree.selection_set(item)

        row = self._get_selected_row()
        if row is None:
            return

        menu = tk.Menu(self.root, tearoff=0)

        if row.left_path:
            menu.add_command(label="Copy Left Path",
                            command=lambda: self._copy_to_clipboard(row.left_path))
        if row.right_path:
            menu.add_command(label="Copy Right Path",
                            command=lambda: self._copy_to_clipboard(row.right_path))

        menu.add_separator()

        if row.left_path and os.path.exists(row.left_path):
            menu.add_command(label="Open Left in Explorer",
                            command=lambda: self._open_in_explorer(row.left_path))
        if row.right_path and os.path.exists(row.right_path):
            menu.add_command(label="Open Right in Explorer",
                            command=lambda: self._open_in_explorer(row.right_path))

        menu.add_separator()

        if row.left_path and row.right_path:
            menu.add_command(label="View Diff",
                            command=lambda: DiffViewer(self.root, row.left_path, row.right_path, row.rel_path))

        menu.tk_popup(event.x_root, event.y_root)

    def _get_selected_row(self) -> ComparisonRow | None:
        """Get the ComparisonRow for the currently selected tree item."""
        sel = self.tree.selection()
        if not sel:
            return None
        values = self.tree.item(sel[0], "values")
        if not values:
            return None
        rel_path = values[0]
        for r in self.all_rows:
            if r.rel_path == rel_path:
                return r
        return None

    def _copy_to_clipboard(self, text: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _open_in_explorer(self, path: str):
        """Open the containing folder in the system file manager."""
        folder = os.path.dirname(path) if os.path.isfile(path) else path
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except OSError:
            pass

    # ------------------------------------------------------------------ copy summary (#8)
    def _copy_summary(self):
        """Copy the summary text to clipboard."""
        text = self.summary_text.get("1.0", tk.END).strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)

    # ------------------------------------------------------------------ re-compare (#11)
    def _recompare(self):
        """Re-run the comparison with current settings."""
        if self.left_var.get().strip() and self.right_var.get().strip():
            self._start_compare()

    # ------------------------------------------------------------------ ignore editor (#2/#9)
    def _ignore_summary(self) -> str:
        patterns = [p.strip() for p in self.ignore_var.get().split(",") if p.strip()]
        return f"{len(patterns)} patterns"

    def _open_ignore_editor(self):
        dlg = IgnorePatternsDialog(self.root, self.ignore_var.get())
        if dlg.result is not None:
            self.ignore_var.set(dlg.result)
            self.ignore_summary_label.configure(text=self._ignore_summary())

    # ------------------------------------------------------------------ search debounce (#13)
    def _schedule_search(self):
        """Debounce search: wait 200ms after last keystroke before filtering."""
        if self._search_after_id is not None:
            self.root.after_cancel(self._search_after_id)
        self._search_after_id = self.root.after(200, self._apply_filters)

    # ------------------------------------------------------------------ placeholder text (#6)
    def _add_placeholder(self, entry: ttk.Entry, var: tk.StringVar, placeholder: str):
        """Add placeholder text to an entry field."""
        def on_focus_in(e):
            if var.get() == placeholder:
                var.set("")
                entry.configure(foreground="")
        def on_focus_out(e):
            if not var.get().strip():
                var.set(placeholder)
                entry.configure(foreground="gray")
        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        # Set initial state only if empty
        if not var.get().strip():
            var.set(placeholder)
            entry.configure(foreground="gray")

    # ------------------------------------------------------------------ showing label click (#5)
    def _on_showing_label_click(self, event):
        if not self._display_all and len(self.all_rows) > self.MAX_DISPLAY_ROWS:
            self._display_all = True
            self._apply_filters()

    # ------------------------------------------------------------------ tooltip (#10)
    def _on_tree_motion(self, event):
        """Show tooltip with full path on hover."""
        item = self.tree.identify_row(event.y)
        if self._tooltip_id:
            self.root.after_cancel(self._tooltip_id)
            self._tooltip_id = None
        self._hide_tooltip()
        if item:
            self._tooltip_id = self.root.after(500, self._show_tooltip, event, item)

    def _show_tooltip(self, event, item):
        values = self.tree.item(item, "values")
        if not values:
            return
        rel_path = values[0]
        row = None
        for r in self.all_rows:
            if r.rel_path == rel_path:
                row = r
                break
        if row is None:
            return

        lines = [rel_path]
        if row.left_path:
            lines.append(f"Left: {row.left_path}")
        if row.right_path:
            lines.append(f"Right: {row.right_path}")

        tip_text = "\n".join(lines)

        self._tooltip = tk.Toplevel(self.root)
        self._tooltip.wm_overrideredirect(True)
        x = self.root.winfo_pointerx() + 15
        y = self.root.winfo_pointery() + 10
        self._tooltip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self._tooltip, text=tip_text, background="#ffffe0",
                        relief="solid", borderwidth=1, font=("Consolas", 9),
                        justify=tk.LEFT, padx=4, pady=2)
        label.pack()

    def _hide_tooltip(self, event=None):
        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None

    # ------------------------------------------------------------------ dialogs

    def _show_history(self):
        """Show comparison history in a dialog."""
        from .history import HistoryManager
        mgr = HistoryManager()
        entries = mgr.load()
        if not entries:
            messagebox.showinfo("History", "No comparison history.")
            return
        # Create a history dialog
        dlg = tk.Toplevel(self.root)
        dlg.title("Comparison History")
        dlg.geometry("700x400")
        dlg.transient(self.root)
        dlg.grab_set()

        frame = ttk.Frame(dlg, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        cols = ("timestamp", "left", "right", "verdict", "score")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=15)
        tree.heading("timestamp", text="Time")
        tree.heading("left", text="Left Directory")
        tree.heading("right", text="Right Directory")
        tree.heading("verdict", text="Verdict")
        tree.heading("score", text="Score")
        tree.column("timestamp", width=140, minwidth=100)
        tree.column("left", width=180, minwidth=100)
        tree.column("right", width=180, minwidth=100)
        tree.column("verdict", width=140, minwidth=100)
        tree.column("score", width=50, minwidth=40)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for entry in entries:
            tree.insert("", tk.END, values=(
                entry.get("timestamp", ""),
                entry.get("left_dir", ""),
                entry.get("right_dir", ""),
                entry.get("verdict", ""),
                entry.get("score", ""),
            ))

        def on_double_click(event):
            sel = tree.selection()
            if sel:
                item = tree.item(sel[0])
                vals = item["values"]
                if len(vals) >= 3:
                    self.left_var.set(str(vals[1]))
                    self.right_var.set(str(vals[2]))
                    dlg.destroy()

        tree.bind("<Double-1>", on_double_click)

        btn_frame = ttk.Frame(dlg, padding=(10, 5))
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Close", command=dlg.destroy).pack(side=tk.RIGHT)

    def _clear_history(self):
        """Clear comparison history."""
        from .history import HistoryManager
        if messagebox.askyesno("Clear History", "Clear all comparison history?"):
            HistoryManager().clear()

    def _show_about(self):
        """Show the About dialog."""
        from . import __version__
        messagebox.showinfo(
            "About DirCompare",
            f"DirCompare v{__version__}\n\n"
            "Compare two directories and determine\n"
            "which is more up to date.\n\n"
            "Uses content fingerprinting, version-string\n"
            "detection, git commit counts, and weighted\n"
            "scoring.\n\n"
            "License: MIT\n"
            "https://forgejo.darkhorseinfosec.com/username/DirCompare"
        )

    def _show_shortcuts(self):
        """Show keyboard shortcuts help."""
        messagebox.showinfo(
            "Keyboard Shortcuts",
            "F5 / Ctrl+Enter \u2014 Start comparison\n"
            "Shift+F5 \u2014 Re-compare\n"
            "Escape \u2014 Cancel comparison\n"
            "Ctrl+E \u2014 Export report\n"
            "Ctrl+S \u2014 Swap directories\n"
            "Ctrl+F \u2014 Focus search box\n"
            "F1 \u2014 About DirCompare"
        )

    # ------------------------------------------------------------------ run
    @classmethod
    def run(cls, left_dir: str | None = None, right_dir: str | None = None):
        """Create root window and start the application."""
        root = tk.Tk()
        app = cls(root)
        # Override with CLI-supplied directories
        if left_dir:
            app.left_var.set(left_dir)
        if right_dir:
            app.right_var.set(right_dir)
        # Auto-start comparison if both directories are provided
        if left_dir and right_dir:
            root.after(100, app._start_compare)
        root.mainloop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(left_dir: str | None = None, right_dir: str | None = None):
    """Convenience function to launch the GUI with optional pre-populated dirs."""
    DirCompareApp.run(left_dir=left_dir, right_dir=right_dir)


if __name__ == "__main__":
    run()
