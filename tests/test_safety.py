from __future__ import annotations

from pathlib import Path

import pytest

from app.library.safety import UnsafePath, is_within, resolve_within, split_relative


def test_relative_path_resolves_inside_root(tmp_path: Path):
    root = tmp_path / "library"
    root.mkdir()
    resolved = resolve_within(root, "Artist/Album/song.mp3")
    assert resolved == root.resolve() / "Artist" / "Album" / "song.mp3"


@pytest.mark.parametrize(
    "evil",
    [
        "../etc/passwd",
        "..",
        "a/../../b",
        "/etc/passwd",
        "\\windows\\system32",
        "C:\\Windows\\win.ini",
        "a\x00b",
        "",
        "   ",
    ],
)
def test_evil_paths_are_rejected(tmp_path: Path, evil: str):
    root = tmp_path / "library"
    root.mkdir()
    with pytest.raises(UnsafePath):
        resolve_within(root, evil)


def test_symlink_escape_is_rejected(tmp_path: Path):
    root = tmp_path / "library"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("nope", encoding="utf-8")
    (root / "link").symlink_to(outside)
    with pytest.raises(UnsafePath):
        resolve_within(root, "link/secret.txt")


def test_dot_segments_are_tolerated(tmp_path: Path):
    root = tmp_path / "library"
    root.mkdir()
    assert resolve_within(root, "./a/./b.mp3") == root.resolve() / "a" / "b.mp3"


def test_split_relative_strips_redundant_segments():
    assert split_relative("a//b/./c") == ["a", "b", "c"]


def test_is_within(tmp_path: Path):
    root = tmp_path / "library"
    root.mkdir()
    inside = root / "a" / "b.mp3"
    assert is_within(root, inside) is True
    assert is_within(root, tmp_path / "other.mp3") is False
