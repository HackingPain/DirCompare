"""
DirCompare application icon.

Generates a simple 48x48 PNG icon programmatically using only stdlib modules.
The icon features a teal background with two folder silhouettes and a
comparison arrow, representing directory comparison.
"""

import base64
import struct
import zlib


def _create_icon_png(size: int = 48) -> bytes:
    """Create a 48x48 PNG icon with a directory-comparison motif.

    Returns raw PNG bytes.  The design is:
    - Teal background (#00838F)
    - Two white folder shapes (left and right)
    - A double-arrow symbol in the center
    """

    # Colours (R, G, B, A)
    TEAL = (0, 131, 143, 255)       # #00838F
    DARK_TEAL = (0, 105, 114, 255)  # slightly darker border/accent
    WHITE = (255, 255, 255, 255)
    LIGHT = (200, 235, 238, 255)    # light accent

    # Start with a teal background
    pixels = [[TEAL for _ in range(size)] for _ in range(size)]

    def _set(x: int, y: int, colour: tuple):
        if 0 <= x < size and 0 <= y < size:
            pixels[y][x] = colour

    def _fill_rect(x0: int, y0: int, x1: int, y1: int, colour: tuple):
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                _set(xx, yy, colour)

    # -- Draw a 1px darker border around the icon --
    for i in range(size):
        _set(i, 0, DARK_TEAL)
        _set(i, size - 1, DARK_TEAL)
        _set(0, i, DARK_TEAL)
        _set(size - 1, i, DARK_TEAL)

    # -- Left folder --
    # Tab part (small rectangle on top-left of folder body)
    _fill_rect(6, 14, 13, 17, WHITE)
    # Folder body
    _fill_rect(6, 17, 21, 34, WHITE)
    # Inner shade to give depth
    _fill_rect(8, 19, 19, 32, LIGHT)

    # -- Right folder --
    # Tab part
    _fill_rect(27, 14, 34, 17, WHITE)
    # Folder body
    _fill_rect(27, 17, 42, 34, WHITE)
    # Inner shade
    _fill_rect(29, 19, 40, 32, LIGHT)

    # -- Double arrow in the centre (between folders) --
    # Right-pointing arrow (top)
    # shaft
    _fill_rect(20, 21, 28, 23, WHITE)
    # arrowhead
    _set(27, 20, WHITE)
    _set(28, 21, WHITE)
    _set(28, 22, WHITE)
    _set(27, 23, WHITE)

    # Left-pointing arrow (bottom)
    # shaft
    _fill_rect(20, 26, 28, 28, WHITE)
    # arrowhead
    _set(21, 25, WHITE)
    _set(20, 26, WHITE)
    _set(20, 27, WHITE)
    _set(21, 28, WHITE)

    # -- Encode as PNG --
    # Raw image data: each row is filter_byte + RGBA pixels
    raw = b""
    for row in pixels:
        raw += b"\x00"  # filter type: None
        for r, g, b, a in row:
            raw += struct.pack("BBBB", r, g, b, a)

    def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)

    ihdr_data = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    # bit depth=8, colour type=6 (RGBA), compression=0, filter=0, interlace=0

    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", ihdr_data)
    png += _png_chunk(b"IDAT", zlib.compress(raw))
    png += _png_chunk(b"IEND", b"")

    return png


# Pre-compute and cache the base64-encoded icon at import time.
_ICON_PNG_BASE64: str = base64.b64encode(_create_icon_png()).decode("ascii")


def get_icon_bytes() -> bytes:
    """Return the raw PNG bytes for the application icon."""
    return base64.b64decode(_ICON_PNG_BASE64)


def get_icon_photo(root):
    """Return a ``tk.PhotoImage`` suitable for use as the application icon.

    Parameters
    ----------
    root : tk.Tk
        The root Tkinter window (needed so the image is associated with the
        correct Tk interpreter).

    Returns
    -------
    tk.PhotoImage
    """
    import tkinter as tk  # local import keeps module usable without display

    return tk.PhotoImage(data=_ICON_PNG_BASE64)
