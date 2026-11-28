from __future__ import annotations

import sys
from typing import Any

from fastapi import APIRouter

from .. import __version__
from .. import _ytdlp as ytdlp
from ..core.ffmpeg import resolve_ffmpeg
from ..core.jsruntime import describe as describe_js
from ..deps import Db, Manager, SettingsDep

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/system")
def system(settings: SettingsDep, db: Db, manager: Manager) -> dict[str, Any]:
    return {
        "version": __version__,
        "python": sys.version.split()[0],
        "ytdlp": ytdlp.version(),
        "ffmpeg": resolve_ffmpeg(),
        "ffmpeg_ok": resolve_ffmpeg() is not None,
        "js_runtime": describe_js(),
        "allow_write": settings.allow_write,
        "auth_required": bool(settings.app_password),
        "max_concurrent": settings.max_concurrent,
        "running": manager.running_count(),
        "tracks": db.count_tracks(),
        "dirs": {
            "data": str(settings.data_dir),
            "downloads": str(settings.download_dir),
            "library": str(settings.library_dir),
            "config": str(settings.config_dir),
        },
        "plugins_dir": str(settings.plugin_dir),
        "plugin_override": (settings.plugin_dir / "yt_dlp").is_dir(),
    }
