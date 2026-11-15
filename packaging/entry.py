"""Nuitka/PyInstaller entry point for the single-file build.

Relative imports need a real module context, so this thin wrapper is the
compilation target instead of ``app/cli.py``.
"""

from app.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
