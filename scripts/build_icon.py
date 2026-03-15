"""
Convert the embedded PNG icon to platform-specific formats for PyInstaller.

Generates:
    assets/icon.png  - Source PNG
    assets/icon.ico  - Windows icon
    assets/icon.icns - macOS icon (if running on macOS, or via PNG fallback)

Requires Pillow (build-time only):
    pip install pillow

Usage:
    python scripts/build_icon.py
"""

import os
import subprocess
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    try:
        from PIL import Image
    except ImportError:
        print("Pillow is required: pip install pillow", file=sys.stderr)
        sys.exit(1)

    from DirCompare.icon import get_icon_bytes

    # Save PNG
    assets_dir = project_root / "assets"
    assets_dir.mkdir(exist_ok=True)

    png_path = assets_dir / "icon.png"
    ico_path = assets_dir / "icon.ico"
    icns_path = assets_dir / "icon.icns"

    png_bytes = get_icon_bytes()
    png_path.write_bytes(png_bytes)
    print(f"Saved PNG: {png_path}")

    # Convert to ICO using Pillow (Windows)
    img = Image.open(png_path)
    img.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
    )
    print(f"Saved ICO: {ico_path}")

    # Convert to ICNS (macOS)
    if sys.platform == "darwin":
        # On macOS, use iconutil for best results
        iconset_dir = assets_dir / "icon.iconset"
        iconset_dir.mkdir(exist_ok=True)

        # Generate required sizes for iconutil
        sizes = {
            "icon_16x16.png": 16,
            "icon_16x16@2x.png": 32,
            "icon_32x32.png": 32,
            "icon_32x32@2x.png": 64,
            "icon_128x128.png": 128,
            "icon_128x128@2x.png": 256,
            "icon_256x256.png": 256,
            "icon_256x256@2x.png": 512,
            "icon_512x512.png": 512,
        }
        for name, size in sizes.items():
            resized = img.resize((size, size), Image.LANCZOS)
            resized.save(iconset_dir / name, format="PNG")

        try:
            subprocess.run(
                ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
                check=True,
            )
            print(f"Saved ICNS: {icns_path}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("  Warning: iconutil not available, creating ICNS via Pillow fallback")
            _icns_fallback(img, icns_path)

        # Clean up iconset
        import shutil
        shutil.rmtree(iconset_dir, ignore_errors=True)
    else:
        # On non-macOS, create ICNS via Pillow fallback so CI can produce it
        _icns_fallback(img, icns_path)


def _icns_fallback(img, icns_path):
    """Create a minimal .icns file using Pillow's ICNS support."""
    try:
        # Pillow can write ICNS directly on any platform
        sizes = [16, 32, 48, 128, 256]
        frames = []
        for s in sizes:
            frames.append(img.resize((s, s), Image.LANCZOS))

        # Pillow ICNS writer uses the first image and appends sizes
        frames[0].save(
            icns_path,
            format="ICNS",
            append_images=frames[1:],
        )
        print(f"Saved ICNS: {icns_path}")
    except Exception as e:
        print(f"  Warning: Could not create ICNS ({e}), macOS build will use no icon")


if __name__ == "__main__":
    main()
