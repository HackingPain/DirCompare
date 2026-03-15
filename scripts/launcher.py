"""PyInstaller entry point for DirCompare.

This thin wrapper avoids relative-import errors when PyInstaller
bundles __main__.py as a top-level script.
"""

from DirCompare.__main__ import main

if __name__ == "__main__":
    main()
