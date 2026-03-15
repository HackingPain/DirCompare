"""
Build standalone executables for DirCompare.

Builds platform-native executables:
    Windows: DirCompare.exe (GUI) + DirCompare-cli.exe (console)
    macOS:   DirCompare.app (GUI bundle) + DirCompare-cli (console)
    Linux:   DirCompare (GUI) + DirCompare-cli (console)

Requires:
    pip install pyinstaller pillow

Usage:
    python scripts/build_exe.py
"""

import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent


def main():
    # Step 1: Generate icon files
    print("Step 1: Generating icon files...")
    build_icon = project_root / "scripts" / "build_icon.py"
    if build_icon.exists():
        subprocess.run([sys.executable, str(build_icon)], check=True)
    else:
        print("  Warning: build_icon.py not found, skipping icon generation")

    # Step 2: Run PyInstaller
    print("\nStep 2: Building executables with PyInstaller...")
    spec_file = project_root / "DirCompare.spec"
    if not spec_file.exists():
        print(f"Error: {spec_file} not found", file=sys.stderr)
        sys.exit(1)

    subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(spec_file), "--clean"],
        cwd=str(project_root),
        check=True,
    )

    # Step 3: Report results
    print("\nBuild complete!")
    dist_dir = project_root / "dist"
    if dist_dir.exists():
        for f in sorted(dist_dir.iterdir()):
            if f.is_file():
                size_mb = f.stat().st_size / (1024 * 1024)
                print(f"  {f.name} ({size_mb:.1f} MB)")
            elif f.is_dir() and f.suffix == ".app":
                # macOS .app bundle — report total size
                total = sum(p.stat().st_size for p in f.rglob("*") if p.is_file())
                size_mb = total / (1024 * 1024)
                print(f"  {f.name}/ ({size_mb:.1f} MB)")

    # Platform-specific notes
    if sys.platform == "darwin":
        print("\nmacOS notes:")
        print("  - DirCompare.app can be dragged to /Applications")
        print("  - DirCompare-cli can be placed in /usr/local/bin")
        print("  - First launch may require: xattr -cr dist/DirCompare.app")
    elif sys.platform == "linux":
        print("\nLinux notes:")
        print("  - Run: chmod +x dist/DirCompare dist/DirCompare-cli")
        print("  - DirCompare-cli can be placed in /usr/local/bin")


if __name__ == "__main__":
    main()
