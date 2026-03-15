# DirCompare Benchmarks

Performance benchmarks for the DirCompare engine.

## Running

```bash
python benchmarks/benchmark.py
```

## What is measured

- **Scan Performance**: Time to walk a directory tree, hash every file (MD5),
  and collect metadata (line counts, word counts, version strings).
- **Compare Performance**: Time to scan both directories and produce a full
  comparison result with scoring.

## Test setup

Benchmarks create temporary directories with varying file counts (100 to
10,000 files). Files are ~1 KB each with semi-random content. The right
directory has ~10% of files modified to create realistic diff scenarios.

Results are deterministic (seeded random) for reproducibility.
