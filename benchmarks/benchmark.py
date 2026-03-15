"""
Performance benchmarks for DirCompare.

Creates temporary directories with varying file counts and measures
scan/compare performance.

Usage:
    python benchmarks/benchmark.py
"""

import os
import random
import shutil
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from DirCompare.engine import compare_directories, scan_directory


def create_test_directory(base_dir: str, file_count: int, avg_size: int = 1024) -> None:
    """Create a directory with N files of varying content."""
    rng = random.Random(42)  # Deterministic for reproducibility
    depth_options = ["", "src/", "src/core/", "lib/", "tests/", "docs/"]

    for i in range(file_count):
        subdir = rng.choice(depth_options)
        ext = rng.choice([".py", ".txt", ".js", ".md", ".json", ".cfg"])
        filename = f"file_{i:06d}{ext}"
        dirpath = os.path.join(base_dir, subdir)
        os.makedirs(dirpath, exist_ok=True)
        filepath = os.path.join(dirpath, filename)

        # Generate semi-random content
        size = max(64, int(rng.gauss(avg_size, avg_size // 3)))
        content = f"# File {i}\n" + "x" * size + "\n"
        with open(filepath, "w") as f:
            f.write(content)


def benchmark_scan(dir_path: str, file_count: int) -> dict:
    """Benchmark scan_directory."""
    tracemalloc.start()
    start = time.perf_counter()
    result = scan_directory(dir_path, [])
    elapsed = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "files": file_count,
        "scanned": len(result),
        "scan_time": elapsed,
        "peak_mb": peak / (1024 * 1024),
    }


def benchmark_compare(left: str, right: str, file_count: int) -> dict:
    """Benchmark compare_directories."""
    tracemalloc.start()
    start = time.perf_counter()
    result = compare_directories(left, right, [])
    elapsed = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "files": file_count,
        "compare_time": elapsed,
        "peak_mb": peak / (1024 * 1024),
        "score": result.score,
    }


def main():
    sizes = [100, 1_000, 5_000, 10_000]
    print("DirCompare Performance Benchmarks")
    print("=" * 60)
    print(f"Python {sys.version.split()[0]}")
    print()

    scan_results = []
    compare_results = []

    for count in sizes:
        print(f"Setting up {count:,} files...", end=" ", flush=True)
        left = tempfile.mkdtemp(prefix=f"dc_bench_left_{count}_")
        right = tempfile.mkdtemp(prefix=f"dc_bench_right_{count}_")
        try:
            create_test_directory(left, count)
            # Right is mostly identical with ~10% different files
            create_test_directory(right, count)
            # Modify some files in right to create differences
            rng = random.Random(99)
            for i in rng.sample(range(count), max(1, count // 10)):
                # Find the file and modify it
                for root, dirs, files in os.walk(right):
                    for f in files:
                        if f.startswith(f"file_{i:06d}"):
                            path = os.path.join(root, f)
                            with open(path, "a") as fh:
                                fh.write("\n# Modified for benchmark\n")
                            break
            print("done.")

            # Benchmark scan
            print(f"  Scanning {count:,} files...", end=" ", flush=True)
            sr = benchmark_scan(left, count)
            scan_results.append(sr)
            print(f"{sr['scan_time']:.2f}s, {sr['peak_mb']:.1f} MB peak")

            # Benchmark compare
            print(f"  Comparing {count:,} files...", end=" ", flush=True)
            cr = benchmark_compare(left, right, count)
            compare_results.append(cr)
            print(f"{cr['compare_time']:.2f}s, {cr['peak_mb']:.1f} MB peak")
            print()

        finally:
            shutil.rmtree(left, ignore_errors=True)
            shutil.rmtree(right, ignore_errors=True)

    # Print summary tables
    print()
    print("Scan Performance")
    print("-" * 55)
    print(f"{'Files':>10} {'Time (s)':>10} {'Files/sec':>12} {'Peak MB':>10}")
    print("-" * 55)
    for r in scan_results:
        fps = r["scanned"] / r["scan_time"] if r["scan_time"] > 0 else 0
        print(f"{r['files']:>10,} {r['scan_time']:>10.2f} {fps:>12,.0f} {r['peak_mb']:>10.1f}")

    print()
    print("Compare Performance")
    print("-" * 55)
    print(f"{'Files':>10} {'Time (s)':>10} {'Files/sec':>12} {'Peak MB':>10}")
    print("-" * 55)
    for r in compare_results:
        fps = r["files"] / r["compare_time"] if r["compare_time"] > 0 else 0
        print(f"{r['files']:>10,} {r['compare_time']:>10.2f} {fps:>12,.0f} {r['peak_mb']:>10.1f}")


if __name__ == "__main__":
    main()
