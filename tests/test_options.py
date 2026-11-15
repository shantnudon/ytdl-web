from __future__ import annotations

from pathlib import Path

from app.core.options import build_opts, format_selector, normalize_preset, parse_rate


def test_unknown_preset_keys_are_dropped():
    preset = normalize_preset({"mode": "audio", "evil": "rm -rf /", "format": "custom"})
    assert "evil" not in preset
    assert "format" not in preset
    assert preset["mode"] == "audio"


def test_invalid_values_fall_back_to_defaults():
    preset = normalize_preset({"mode": "laser", "quality": "99999", "audio_format": "exe"})
    assert preset["mode"] == "video"
    assert preset["quality"] == "best"
    assert preset["audio_format"] == "mp3"


def test_outtmpl_is_normalized():
    assert normalize_preset({"outtmpl": "a/%(title)s"})["outtmpl"].endswith("%(ext)s")
    assert ".." not in normalize_preset({"outtmpl": "../../x.%(ext)s"})["outtmpl"]


def test_format_selector():
    assert format_selector({"quality": "best"}) == "bv*+ba/b"
    assert "[height<=1080]" in format_selector({"quality": "1080"})


def test_parse_rate():
    assert parse_rate("") is None
    assert parse_rate(None) is None
    assert parse_rate("500K") == 500 * 1024
    assert parse_rate("1.5M") == int(1.5 * 1024**2)
    assert parse_rate("nonsense") is None


def test_audio_opts(tmp_path: Path):
    opts = build_opts(
        {"mode": "audio", "audio_format": "mp3", "audio_quality": "320"},
        download_dir=tmp_path,
    )
    assert opts["format"] == "bestaudio/best"
    assert opts["paths"]["home"] == str(tmp_path)
    postprocessors = opts["postprocessors"]
    audio_pp = next(pp for pp in postprocessors if pp["key"] == "FFmpegExtractAudio")
    assert audio_pp["preferredcodec"] == "mp3"
    assert audio_pp["preferredquality"] == "320"


def test_video_opts(tmp_path: Path):
    opts = build_opts({"quality": "720"}, download_dir=tmp_path)
    assert opts["merge_output_format"] == "mp4"
    assert "[height<=720]" in opts["format"]
    assert opts["noplaylist"] is False


def test_playlist_and_archive_opts(tmp_path: Path):
    opts = build_opts(
        {"playlist_items": "1-3", "archive": True},
        download_dir=tmp_path,
        archive_path=tmp_path / "archive.txt",
    )
    assert opts["playlist_items"] == "1-3"
    assert opts["download_archive"].endswith("archive.txt")

    single = build_opts({"allow_playlist": False}, download_dir=tmp_path)
    assert single["noplaylist"] is True
