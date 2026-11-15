from __future__ import annotations

from pathlib import Path

from app.library import tags


def test_probe_empty_file_does_not_raise(tmp_path: Path):
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"definitely not audio")
    meta = tags.probe_file(junk)
    assert meta["title"] == ""
    assert meta["has_art"] is False


def test_write_and_read_tags(silent_mp3: Path):
    tags.write_tags(
        silent_mp3,
        {
            "title": "Hello World",
            "artist": "AC/DC",
            "album": "Back in Black",
            "albumartist": "AC/DC",
            "track": "3",
            "year": "1980",
            "genre": "Rock",
        },
    )
    meta = tags.probe_file(silent_mp3)
    assert meta["title"] == "Hello World"
    assert meta["artist"] == "AC/DC"
    assert meta["album"] == "Back in Black"
    assert meta["track"] == "3"
    assert meta["year"] == "1980"
    assert meta["genre"] == "Rock"
    assert meta["duration"] > 0


def test_clearing_a_tag(silent_mp3: Path):
    tags.write_tags(silent_mp3, {"artist": "Someone"})
    assert tags.probe_file(silent_mp3)["artist"] == "Someone"
    tags.write_tags(silent_mp3, {"artist": ""})
    assert tags.probe_file(silent_mp3)["artist"] == ""


def test_cover_art_roundtrip(silent_mp3: Path, png_1px: bytes):
    assert tags.probe_file(silent_mp3)["has_art"] is False
    tags.set_art(silent_mp3, png_1px, "image/png")
    assert tags.probe_file(silent_mp3)["has_art"] is True
    tags.remove_art(silent_mp3)
    assert tags.probe_file(silent_mp3)["has_art"] is False


def test_art_is_rejected_for_unsupported_format(tmp_path: Path, png_1px: bytes):
    wav = tmp_path / "x.wav"
    wav.write_bytes(b"RIFF")
    try:
        tags.set_art(wav, png_1px, "image/png")
    except ValueError:
        return
    raise AssertionError("expected ValueError for wav cover art")
