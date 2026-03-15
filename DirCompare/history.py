"""
Comparison history storage and retrieval.
Stores summaries of past comparisons in a JSON file.
"""

import json
import os
from typing import Optional


DEFAULT_HISTORY_PATH = os.path.join(os.path.expanduser("~"), ".dircompare_history.json")
DEFAULT_MAX_ENTRIES = 50


class HistoryManager:
    """Manage a persistent history of comparison summaries."""

    def __init__(
        self,
        path: str = DEFAULT_HISTORY_PATH,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ):
        self._path = path
        self._max_entries = max_entries

    def load(self) -> list[dict]:
        """Load history entries from disk. Returns empty list on error."""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return []

    def save_entry(self, entry: dict) -> None:
        """Append a comparison summary to history (newest first)."""
        entries = self.load()
        entries.insert(0, entry)
        # Trim to max entries
        entries = entries[: self._max_entries]
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2)
        except OSError:
            pass

    def clear(self) -> None:
        """Clear all history."""
        try:
            if os.path.exists(self._path):
                os.remove(self._path)
        except OSError:
            pass

    @staticmethod
    def make_entry(result) -> dict:
        """Create a history entry from a ComparisonResult."""
        if result.score < 0:
            verdict = "LEFT is more up to date"
        elif result.score > 0:
            verdict = "RIGHT is more up to date"
        else:
            verdict = "Directories are equivalent"
        return {
            "timestamp": result.timestamp,
            "left_dir": result.left_dir,
            "right_dir": result.right_dir,
            "score": result.score,
            "confidence": result.confidence,
            "verdict": verdict,
            "left_file_count": result.left_file_count,
            "right_file_count": result.right_file_count,
        }

    def format_history(self) -> str:
        """Format history as a human-readable string."""
        entries = self.load()
        if not entries:
            return "No comparison history."
        lines = [f"Comparison History ({len(entries)} entries):", ""]
        for i, entry in enumerate(entries, 1):
            lines.append(f"  {i}. [{entry.get('timestamp', 'N/A')}]")
            lines.append(f"     Left:  {entry.get('left_dir', 'N/A')}")
            lines.append(f"     Right: {entry.get('right_dir', 'N/A')}")
            lines.append(
                f"     Result: {entry.get('verdict', 'N/A')} "
                f"(score: {entry.get('score', 'N/A')}, "
                f"confidence: {entry.get('confidence', 'N/A')})"
            )
            lines.append("")
        return "\n".join(lines)
