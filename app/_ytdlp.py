"""The single gateway to yt-dlp.

Importing yt-dlp directly anywhere else is a bug: the extractor plugin
directory must be placed on ``sys.path`` *before* the first import so users
can upgrade yt-dlp without reinstalling the app (see ``app.cli.update_extractors``).
"""

from __future__ import annotations

import sys
from contextlib import suppress
from typing import Any

from .config import get_settings
from .core.jsruntime import detect as detect_js_runtimes


def _apply_plugin_path() -> None:
    try:
        plugin_dir = get_settings().plugin_dir
    except Exception:  # pragma: no cover - never block startup on config issues
        return
    if (plugin_dir / "yt_dlp").is_dir():
        entry = str(plugin_dir)
        if entry not in sys.path:
            sys.path.insert(0, entry)


_apply_plugin_path()

import yt_dlp  # noqa: E402
from yt_dlp.utils import DownloadCancelled, DownloadError  # noqa: E402,F401

__all__ = ["DownloadCancelled", "DownloadError", "make", "probe", "version"]


def version() -> str:
    return getattr(yt_dlp.version, "__version__", "unknown")


def make(opts: dict[str, Any]) -> yt_dlp.YoutubeDL:
    return yt_dlp.YoutubeDL(opts)


class _QuietLogger:
    def debug(self, msg: str) -> None:  # noqa: D102
        pass

    def info(self, msg: str) -> None:  # noqa: D102
        pass

    def warning(self, msg: str) -> None:  # noqa: D102
        pass

    def error(self, msg: str) -> None:  # noqa: D102
        pass


def probe(
    url: str, *, playlist_limit: int = 100, cookies_file: str | None = None
) -> dict[str, Any]:
    """Fetch metadata (and, for playlists, a flat entry list) without downloading."""
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noprogress": True,
        "extract_flat": "in_playlist",
        "playlistend": playlist_limit,
        "socket_timeout": 20,
        "logger": _QuietLogger(),
        "noplaylist": False,
    }
    runtimes = detect_js_runtimes()
    if runtimes:
        opts["js_runtimes"] = runtimes
    if cookies_file:
        opts["cookiefile"] = cookies_file

    ydl = make(opts)
    try:
        info = ydl.extract_info(url, download=False)
    finally:
        _safe_close(ydl)

    if not info:
        raise DownloadError("no metadata returned")

    if info.get("_type") == "playlist":
        entries = []
        for entry in info.get("entries") or []:
            if not entry:
                continue
            entries.append(
                {
                    "id": entry.get("id"),
                    "title": entry.get("title"),
                    "url": entry.get("url") or entry.get("webpage_url"),
                    "duration": entry.get("duration"),
                    "uploader": entry.get("uploader") or entry.get("channel"),
                }
            )
        return {
            "type": "playlist",
            "id": info.get("id"),
            "title": info.get("title"),
            "uploader": info.get("uploader") or info.get("channel"),
            "entry_count": info.get("playlist_count") or len(entries),
            "entries": entries,
            "formats": [],
        }

    formats = []
    for fmt in (info.get("formats") or [])[:60]:
        formats.append(
            {
                "format_id": fmt.get("format_id"),
                "ext": fmt.get("ext"),
                "resolution": fmt.get("resolution") or fmt.get("format_note"),
                "fps": fmt.get("fps"),
                "vcodec": fmt.get("vcodec"),
                "acodec": fmt.get("acodec"),
                "tbr": fmt.get("tbr"),
                "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
            }
        )
    return {
        "type": "video",
        "id": info.get("id"),
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "upload_date": info.get("upload_date"),
        "view_count": info.get("view_count"),
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "formats": formats,
    }


def _safe_close(ydl: Any) -> None:
    with suppress(Exception):
        ydl.close()
