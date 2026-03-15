# Plugin API

DirCompare supports custom scoring plugins that extend the comparison engine with new signals.

## Plugin Locations

Plugins are Python files placed in:

- `~/.dircompare/plugins/` — user-level plugins
- `./.dircompare/plugins/` — project-level plugins
- Additional directories via `--plugin-dir`

## Creating a Plugin

Each plugin file must define three things:

```python
# ~/.dircompare/plugins/mytime_scorer.py

name = "mtime_scorer"   # Unique identifier
weight = 1              # Score multiplier

def score(left_files, right_files):
    """Compare directories based on average file modification time.

    Parameters
    ----------
    left_files : dict[str, FileInfo]
        Files from the left directory, keyed by relative path.
    right_files : dict[str, FileInfo]
        Files from the right directory, keyed by relative path.

    Returns
    -------
    int
        Negative = left is newer, positive = right is newer, 0 = neutral.
    """
    # Your scoring logic here
    return 0
```

## FileInfo Object

Each file in the dictionaries is a `FileInfo` dataclass with these attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `rel_path` | str | Relative path from directory root |
| `abs_path` | str | Absolute filesystem path |
| `size` | int | File size in bytes |
| `content_hash` | str | MD5 or SHA-256 hex digest |
| `hash_algorithm` | str | `"md5"` or `"sha256"` |
| `is_binary` | bool | Whether the file is binary |
| `line_count` | int | Number of lines (text files only) |
| `word_count` | int | Number of words (text files only) |
| `char_count` | int | Number of characters (text files only) |
| `version_strings` | list[str] | Detected version strings |
| `error` | str or None | Error message if scanning failed |

## Example: File Count Scorer

```python
name = "file_count"
weight = 1

def score(left_files, right_files):
    """Side with more files scores higher."""
    diff = len(right_files) - len(left_files)
    if abs(diff) > 5:
        return 1 if diff > 0 else -1
    return 0
```

## Error Handling

- Plugin errors are caught and reported as warnings — they never crash the comparison.
- If a plugin is missing `name`, `weight`, or `score`, it is skipped with a warning.
- Plugins are loaded in alphabetical filename order.
- If two plugins share the same `name`, only the first is loaded.

## Disabling Plugins

```bash
dircompare -l a/ -r b/ --no-plugins
```
