# Scoring Algorithm

DirCompare uses a weighted scoring system to determine which directory is more up to date.

## Signals

Four independent signals are combined:

### 1. Unique Files (default weight: 3)

Files that exist in only one directory contribute to that side's score. Each unique file adds ±weight to the total.

### 2. Content Analysis (default weight: 1)

For files that exist in both directories but have different content:

- **Line count comparison** — more lines suggests newer (active development adds code)
- **Word count comparison** — more words suggests newer
- **Per-file version strings** — if one file contains a higher version string

A >10% difference in content volume triggers this signal.

### 3. Version Strings (default weight: 2)

DirCompare scans all text files for version patterns:

- Semantic versions: `v1.2.3`, `1.2.3`
- Version assignments: `version = "1.0"`, `__version__ = "2.1"`
- Date-based versions: `2024-01-15`

The highest version found on each side is compared.

### 4. Git Commits (default weight: 2)

If either directory is inside a git repository, DirCompare counts the total commits. More commits suggests more development activity.

## Score Interpretation

| Score | Meaning |
|-------|---------|
| Negative | Left directory is more up to date |
| Zero | Directories are equivalent |
| Positive | Right directory is more up to date |

## Confidence Levels

| Level | Condition |
|-------|-----------|
| High | \|score\| ≥ 8 |
| Medium | \|score\| ≥ 3 |
| Low | \|score\| < 3 |

## Custom Weights

Override via CLI:

```bash
dircompare -l a/ -r b/ --weights 5:1:3:2
```

Format: `unique:content:version:git`

Or adjust in the GUI via Settings.

## Plugins

Custom scoring signals can be added via the [Plugin API](plugin-api.md).
