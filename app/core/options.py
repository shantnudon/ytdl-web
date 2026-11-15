"""Translate a small, validated preset dict into yt-dlp options.

Everything the UI can change goes through :func:`normalize_preset`, so user
input can never inject arbitrary yt-dlp options.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .jsruntime import detect as detect_js_runtimes

QUALITY_HEIGHTS = {
    "2160": 2160,
    "1440": 1440,
    "1080": 1080,
    "720": 720,
    "480": 480,
    "360": 360,
}

AUDIO_CODECS = {"mp3", "m4a", "opus", "flac", "aac", "wav"}
AUDIO_QUALITIES = {"0", "320", "256", "192", "128"}
SPONSORBLOCK_MODES = {"off", "mark", "remove"}
SPONSORBLOCK_CATEGORIES = [
    "sponsor",
    "selfpromo",
    "interaction",
    "intro",
    "outro",
    "preview",
    "music_offtopic",
]

DEFAULT_OUTTMPL = "%(title)s [%(id)s].%(ext)s"

DEFAULT_PRESET: dict[str, Any] = {
    "mode": "video",  # video | audio
    "quality": "best",
    "audio_format": "mp3",
    "audio_quality": "0",
    "outtmpl": DEFAULT_OUTTMPL,
    "restrict_filenames": True,
    "allow_playlist": True,
    "playlist_items": "",
    "subtitles": False,
    "subtitle_langs": ["en"],
    "embed_subs": False,
    "embed_metadata": True,
    "embed_thumbnail": True,
    "sponsorblock": "off",
    "write_info_json": False,
    "archive": True,
    "rate_limit": "",
    "concurrent_fragments": 4,
}

_RATE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([kmg]?)i?b?$", re.IGNORECASE)
_RATE_UNITS = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}


def parse_rate(value: str | int | None) -> int | None:
    """'5M' -> 5242880 bytes/s. Empty/invalid -> None (unlimited)."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    match = _RATE_RE.match(str(value).strip())
    if not match:
        return None
    amount, unit = match.groups()
    rate = int(float(amount) * _RATE_UNITS[unit.lower()])
    return rate if rate > 0 else None


def normalize_preset(raw: dict[str, Any] | None) -> dict[str, Any]:
    preset = dict(DEFAULT_PRESET)
    if not raw:
        return preset
    for key in DEFAULT_PRESET:
        if key in raw:
            preset[key] = raw[key]

    if preset["mode"] not in ("video", "audio"):
        preset["mode"] = "video"
    if preset["quality"] not in ("best", *QUALITY_HEIGHTS.keys()):
        preset["quality"] = "best"
    if preset["audio_format"] not in AUDIO_CODECS:
        preset["audio_format"] = "mp3"
    if str(preset["audio_quality"]) not in AUDIO_QUALITIES:
        preset["audio_quality"] = "0"
    if preset["sponsorblock"] not in SPONSORBLOCK_MODES:
        preset["sponsorblock"] = "off"

    langs = preset.get("subtitle_langs") or ["en"]
    if isinstance(langs, str):
        langs = [part.strip() for part in langs.split(",") if part.strip()]
    preset["subtitle_langs"] = [str(lang)[:16] for lang in langs][:10] or ["en"]

    outtmpl = str(preset.get("outtmpl") or DEFAULT_OUTTMPL).strip()
    outtmpl = outtmpl.replace("\\", "/").lstrip("/")
    if ".." in outtmpl.split("/"):
        outtmpl = DEFAULT_OUTTMPL
    if "%(ext)s" not in outtmpl:
        outtmpl = f"{outtmpl}.%(ext)s"
    preset["outtmpl"] = outtmpl[:300]

    try:
        preset["concurrent_fragments"] = max(1, min(16, int(preset["concurrent_fragments"])))
    except (TypeError, ValueError):
        preset["concurrent_fragments"] = 4

    preset["playlist_items"] = str(preset.get("playlist_items") or "").strip()[:200]
    preset["subtitle_langs"] = preset["subtitle_langs"]
    return preset


def format_selector(preset: dict[str, Any]) -> str:
    quality = preset["quality"]
    if quality == "best":
        return "bv*+ba/b"
    height = QUALITY_HEIGHTS[quality]
    return (
        f"bv*[height<={height}]+ba/b[height<={height}]/"
        f"bv*[height<={height}]+ba/b"
    )


def build_opts(
    preset: dict[str, Any],
    *,
    download_dir: Path,
    cookies_file: Path | None = None,
    ffmpeg_path: str | None = None,
    archive_path: Path | None = None,
    progress_hooks: list[Callable[[dict], None]] | None = None,
    postprocessor_hooks: list[Callable[[dict], None]] | None = None,
    logger: Any = None,
) -> dict[str, Any]:
    preset = normalize_preset(preset)
    pps: list[dict[str, Any]] = []

    opts: dict[str, Any] = {
        "paths": {"home": str(download_dir), "temp": str(download_dir / ".tmp")},
        "outtmpl": {"default": preset["outtmpl"]},
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": not bool(preset["allow_playlist"]),
        "restrictfilenames": bool(preset["restrict_filenames"]),
        "windowsfilenames": False,
        "continuedl": True,
        "overwrites": False,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": preset["concurrent_fragments"],
        "ignoreerrors": False,
        "socket_timeout": 30,
    }

    if preset["playlist_items"]:
        opts["playlist_items"] = preset["playlist_items"]

    rate = parse_rate(preset["rate_limit"])
    if rate:
        opts["ratelimit"] = rate

    if preset["mode"] == "audio":
        opts["format"] = "bestaudio/best"
        pps.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": preset["audio_format"],
                "preferredquality": str(preset["audio_quality"]),
                "nopostoverwrites": False,
            }
        )
    else:
        opts["format"] = format_selector(preset)
        opts["merge_output_format"] = "mp4"

    if preset["subtitles"] or preset["embed_subs"]:
        opts["writesubtitles"] = True
        opts["writeautomaticsub"] = True
        opts["subtitleslangs"] = preset["subtitle_langs"]
        if preset["embed_subs"]:
            opts["embedsubtitles"] = True

    if preset["embed_thumbnail"]:
        opts["writethumbnail"] = True
        if preset["mode"] == "audio":
            pps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
        pps.append({"key": "EmbedThumbnail"})

    if preset["embed_metadata"]:
        pps.append({"key": "FFmpegMetadata"})

    if preset["sponsorblock"] != "off":
        pps.append(
            {
                "key": "SponsorBlock",
                "categories": SPONSORBLOCK_CATEGORIES,
                "when": "after_filter",
            }
        )
        if preset["sponsorblock"] == "remove":
            pps.append(
                {
                    "key": "ModifyChapters",
                    "remove_sponsor_segments": SPONSORBLOCK_CATEGORIES,
                }
            )

    if pps:
        opts["postprocessors"] = pps

    if preset["write_info_json"]:
        opts["writeinfojson"] = True

    if preset["archive"] and archive_path:
        opts["download_archive"] = str(archive_path)

    if cookies_file and Path(cookies_file).is_file():
        opts["cookiefile"] = str(cookies_file)

    if ffmpeg_path:
        opts["ffmpeg_location"] = ffmpeg_path

    runtimes = detect_js_runtimes()
    if runtimes:
        opts["js_runtimes"] = runtimes

    if progress_hooks:
        opts["progress_hooks"] = progress_hooks
    if postprocessor_hooks:
        opts["postprocessor_hooks"] = postprocessor_hooks
    if logger is not None:
        opts["logger"] = logger

    return opts
