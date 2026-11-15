"""Path jailing and crash-safe file replacement.

Every filesystem mutation in the library goes through this module. If a path
can escape the configured root, it is rejected before touching the disk.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class UnsafePath(ValueError):
    """Raised when a user-supplied path leaves the library root."""


def resolve_root(root: Path | str) -> Path:
    path = Path(root).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve(strict=True)


def split_relative(rel: str) -> list[str]:
    if rel is None:
        raise UnsafePath("missing path")
    if "\x00" in rel:
        raise UnsafePath("null byte in path")
    rel = rel.strip()
    if not rel:
        raise UnsafePath("empty path")
    if rel.startswith(("/", "\\")):
        raise UnsafePath("absolute paths are not allowed")
    if len(rel) > 1 and rel[1] == ":":
        raise UnsafePath("absolute paths are not allowed")
    parts = [part for part in rel.replace("\\", "/").split("/") if part not in ("", ".")]
    if not parts:
        raise UnsafePath("empty path")
    if any(part == ".." for part in parts):
        raise UnsafePath("parent traversal is not allowed")
    return parts


def resolve_within(root: Path | str, rel: str) -> Path:
    """Resolve *rel* under *root*, rejecting traversal and symlink escapes."""
    base = resolve_root(root)
    candidate = base.joinpath(*split_relative(rel))
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:  # pragma: no cover - platform specific
        raise UnsafePath(str(exc)) from exc
    if resolved != base and base not in resolved.parents:
        raise UnsafePath("path escapes the library root")
    return resolved


def relative_to_root(root: Path | str, path: Path) -> str:
    base = resolve_root(root)
    return path.resolve().relative_to(base).as_posix()


def is_within(root: Path | str, path: Path) -> bool:
    try:
        base = resolve_root(root)
        resolved = path.resolve()
    except (OSError, UnsafePath):
        return False
    return resolved == base or base in resolved.parents


@contextmanager
def atomic_write(path: Path) -> Iterator[Path]:
    """Yield a temp sibling of *path*; atomically replace on clean exit.

    Callers copy the original into the temp file and mutate the copy, so a
    crash mid-write can never truncate the user's audio file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        yield tmp_path
        if path.exists():
            shutil.copymode(path, tmp_path)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
