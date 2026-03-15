# CLI Reference

## Usage

```
dircompare [OPTIONS] [DIRECTORIES...]
python -m DirCompare [OPTIONS] [DIRECTORIES...]
```

## Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--left PATH` | `-l` | | Left directory path |
| `--right PATH` | `-r` | | Right directory path |
| `--format FMT` | `-f` | `text` | Output format: `text`, `csv`, `json`, `html` |
| `--output FILE` | `-o` | stdout | Write report to file |
| `--ignore PATS` | `-i` | (defaults) | Comma-separated ignore patterns |
| `--gitignore` | | off | Parse `.gitignore` files for extra patterns |
| `--weights W` | | `3:1:2:2` | Custom scoring weights `unique:content:version:git` |
| `--quiet` | `-q` | off | Suppress progress output |
| `--hash-algorithm` | `-H` | `md5` | Hash algorithm: `md5` or `sha256` |
| `--watch` | | off | Watch for changes and re-compare automatically |
| `--watch-interval` | | `5.0` | Seconds between polls in watch mode |
| `--history` | | | Show comparison history and exit |
| `--history-clear` | | | Clear comparison history and exit |
| `--no-history` | | off | Skip saving this comparison to history |
| `--no-plugins` | | off | Disable plugin loading |
| `--plugin-dir DIR` | | | Additional plugin directory (repeatable) |

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Directories are equivalent |
| `1` | Error (invalid path, permission denied, etc.) |
| `10` | Left directory is more up to date |
| `20` | Right directory is more up to date |

## Examples

```bash
# Basic comparison
dircompare -l project_v1/ -r project_v2/

# JSON report to file
dircompare -l src/ -r backup/ -f json -o report.json

# SHA-256 hashing with custom weights
dircompare -l repo1/ -r repo2/ -H sha256 --weights 5:1:3:2

# Watch mode with .gitignore support
dircompare -l dev/ -r staging/ --gitignore --watch

# Quiet mode for scripting
dircompare -l a/ -r b/ -q && echo "equivalent" || echo "different"
```
