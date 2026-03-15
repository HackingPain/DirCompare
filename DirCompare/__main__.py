"""
DirCompare entry point.

Usage:
    python -m DirCompare                      # launches GUI (default)
    python -m DirCompare --left L --right R   # CLI mode
"""

import argparse
import logging
import os
import sys
import time

logger = logging.getLogger("DirCompare")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="DirCompare",
        description="Compare two directories and determine which is more up to date.",
    )
    parser.add_argument(
        "--left", "-l",
        help="Left directory path (required for CLI mode)",
    )
    parser.add_argument(
        "--right", "-r",
        help="Right directory path (required for CLI mode)",
    )
    from .engine import DEFAULT_IGNORE_PATTERNS
    _default_ignore = ",".join(DEFAULT_IGNORE_PATTERNS)
    parser.add_argument(
        "--ignore", "-i",
        default=_default_ignore,
        help=(
            "Comma-separated ignore patterns (default covers Python, Node, "
            "version control, IDE files, OS artifacts, build outputs, and more)"
        ),
    )
    parser.add_argument(
        "--gitignore",
        action="store_true",
        default=False,
        help="Enable .gitignore parsing for additional ignore patterns",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["text", "csv", "json", "html"],
        default="text",
        help="Output format: text (default), csv, json, html",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--weights",
        default=None,
        help=(
            "Custom scoring weights as unique:content:version:git "
            "e.g. '3:1:2:2' (default uses ScoringWeights defaults)"
        ),
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        default=False,
        help="Suppress progress output, only show result",
    )
    parser.add_argument(
        "--hash-algorithm", "-H",
        choices=["md5", "sha256"],
        default="md5",
        help="Hash algorithm for content fingerprinting: md5 (default, faster) or sha256 (more secure)",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        default=False,
        help="Enable hash caching to speed up repeated comparisons "
             "(stores .dircompare_cache.json in each scanned directory)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Explicitly disable hash caching (default behaviour)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        default=False,
        help="Watch directories for changes and re-run comparison automatically",
    )
    parser.add_argument(
        "--watch-interval",
        type=float,
        default=5.0,
        help="Seconds between filesystem polls in watch mode (default: 5.0, minimum: 0.5)",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        default=False,
        help="Show comparison history and exit",
    )
    parser.add_argument(
        "--history-clear",
        action="store_true",
        default=False,
        help="Clear comparison history and exit",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        default=False,
        help="Do not save this comparison to history",
    )
    parser.add_argument(
        "--no-plugins",
        action="store_true",
        default=False,
        help="Disable plugin loading",
    )
    parser.add_argument(
        "--plugin-dir",
        action="append",
        default=None,
        help="Additional directory to search for plugins (can be specified multiple times)",
    )
    parser.add_argument(
        "directories",
        nargs="*",
        help="Optional: two directory paths to pre-fill (GUI mode) or compare (CLI with --left/--right)",
    )
    return parser


def _parse_weights(weights_str: str):
    """Parse a weights string like '3:1:2:2' into a ScoringWeights instance."""
    from .engine import ScoringWeights

    parts = weights_str.split(":")
    if len(parts) != 4:
        logger.error(
            "--weights must be in the format unique:content:version:git "
            "(e.g. '3:1:2:2')"
        )
        sys.exit(1)
    try:
        values = [int(p) for p in parts]
    except ValueError:
        logger.error("All weight values must be integers.")
        sys.exit(1)
    return ScoringWeights(
        unique_file=values[0],
        content_analysis=values[1],
        version_string=values[2],
        git_commits=values[3],
    )


def _progress_callback(fraction: float, message: str = "") -> None:
    """Print a text-based progress indicator to stderr."""
    bar_width = 40
    filled = int(bar_width * fraction)
    bar = "#" * filled + "-" * (bar_width - filled)
    pct = int(fraction * 100)
    suffix = f"  {message}" if message else ""
    line = f"\r  [{bar}] {pct:3d}%{suffix}"
    # Pad to overwrite previous longer lines
    print(f"{line:<80}", end="", file=sys.stderr, flush=True)
    if fraction >= 1.0:
        print(file=sys.stderr)


def _run_cli(args: argparse.Namespace) -> int:
    """Run the CLI comparison and return the exit code."""
    from .engine import (
        ScoringWeights,
        compare_directories,
        export_report_csv,
        export_report_html,
        export_report_json,
        export_report_txt,
    )

    # Validate directories
    left_dir = os.path.abspath(args.left)
    right_dir = os.path.abspath(args.right)

    if not os.path.isdir(left_dir):
        logger.error("Left directory does not exist: %s", left_dir)
        return 1
    if not os.path.isdir(right_dir):
        logger.error("Right directory does not exist: %s", right_dir)
        return 1

    # Parse ignore patterns
    ignore_patterns = [p.strip() for p in args.ignore.split(",") if p.strip()]

    # Parse weights
    if args.weights:
        weights = _parse_weights(args.weights)
    else:
        weights = ScoringWeights()

    # Progress callback
    progress_cb = None if args.quiet else _progress_callback

    # Cache setting
    use_cache = getattr(args, 'cache', False) and not getattr(args, 'no_cache', False)

    # Run comparison
    start_time = time.monotonic()
    try:
        result = compare_directories(
            left_dir=left_dir,
            right_dir=right_dir,
            ignore_patterns=ignore_patterns,
            weights=weights,
            use_gitignore=args.gitignore,
            progress_callback=progress_cb,
            hash_algorithm=args.hash_algorithm,
            plugins_enabled=not getattr(args, 'no_plugins', False),
            plugin_dirs=getattr(args, 'plugin_dir', None),
            use_cache=use_cache,
        )
    except PermissionError as e:
        logger.error("Permission denied: %s", e)
        return 1
    except OSError as e:
        logger.error("%s", e)
        return 1

    elapsed = time.monotonic() - start_time
    if not args.quiet:
        print(
            f"Comparison completed in {elapsed:.1f}s  [{result.timestamp}]",
            file=sys.stderr,
        )

    # Format the report
    if args.format == "csv":
        report = export_report_csv(result)
    elif args.format == "json":
        report = export_report_json(result)
    elif args.format == "html":
        report = export_report_html(result)
    else:
        report = export_report_txt(result)

    # Output
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(report)
            if not args.quiet:
                print(f"Report written to: {args.output}", file=sys.stderr)
        except OSError as e:
            logger.error("Error writing output file: %s", e)
            return 1
    else:
        print(report)

    # Save to history
    if not getattr(args, 'no_history', False):
        try:
            from .history import HistoryManager
            HistoryManager().save_entry(HistoryManager.make_entry(result))
        except Exception:
            pass  # History saving is non-critical

    # Watch mode: re-run on changes
    if getattr(args, "watch", False):
        from .watcher import watch_and_compare

        def rerun():
            nonlocal result, report
            try:
                result = compare_directories(
                    left_dir=left_dir,
                    right_dir=right_dir,
                    ignore_patterns=ignore_patterns,
                    weights=weights,
                    use_gitignore=args.gitignore,
                    progress_callback=progress_cb,
                    hash_algorithm=args.hash_algorithm,
                    plugins_enabled=not getattr(args, 'no_plugins', False),
                    plugin_dirs=getattr(args, 'plugin_dir', None),
                    use_cache=use_cache,
                )
            except Exception as e:
                logger.error("Comparison failed: %s", e)
                return
            if args.format == "csv":
                report = export_report_csv(result)
            elif args.format == "json":
                report = export_report_json(result)
            elif args.format == "html":
                report = export_report_html(result)
            else:
                report = export_report_txt(result)
            if args.output:
                try:
                    with open(args.output, "w", encoding="utf-8") as f:
                        f.write(report)
                except OSError as e:
                    logger.error("Error writing output file: %s", e)
            else:
                print(report)

        watch_and_compare(
            left_dir=left_dir,
            right_dir=right_dir,
            ignore_patterns=ignore_patterns,
            interval=getattr(args, "watch_interval", 5.0),
            run_comparison=rerun,
        )
        return 0  # Watch mode always exits cleanly

    # Exit code: 0 = equivalent, 10 = left newer, 20 = right newer
    # (1 is reserved for errors above)
    if result.score < 0:
        return 10
    elif result.score > 0:
        return 20
    else:
        return 0


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Configure logging: errors always shown, info suppressed with --quiet
    log_level = logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        stream=sys.stderr,
    )

    # Handle history commands
    if getattr(args, 'history', False):
        from .history import HistoryManager
        print(HistoryManager().format_history())
        return
    if getattr(args, 'history_clear', False):
        from .history import HistoryManager
        HistoryManager().clear()
        print("History cleared.", file=sys.stderr)
        return

    # Merge positional directories into --left/--right
    if hasattr(args, 'directories') and args.directories:
        if len(args.directories) >= 1 and not args.left:
            args.left = args.directories[0]
        if len(args.directories) >= 2 and not args.right:
            args.right = args.directories[1]
        if len(args.directories) > 2:
            logger.error("At most two directory paths can be provided.")
            sys.exit(1)

    # If --left and --right are both provided and no GUI-forcing flag, run CLI mode
    if args.left and args.right:
        exit_code = _run_cli(args)
        sys.exit(exit_code)

    # Default: GUI mode
    try:
        from .gui import run
        run(
            left_dir=getattr(args, 'left', None) or None,
            right_dir=getattr(args, 'right', None) or None,
        )
    except ImportError as e:
        logger.error(
            "Could not import GUI module: %s\n"
            "Make sure gui.py is in the DirCompare package directory.\n"
            "For CLI mode, use: python -m DirCompare --left <dir> --right <dir>",
            e,
        )
        sys.exit(1)
    except Exception as e:
        logger.error("Error launching GUI: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
