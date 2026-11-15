from __future__ import annotations

import shutil
from pathlib import Path

from ..config import get_settings


def resolve_ffmpeg() -> str | None:
    """FFMPEG_PATH -> bundled imageio-ffmpeg -> PATH."""
    explicit = get_settings().ffmpeg_path
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return str(candidate)
    try:  # only present in binary builds / when the extra is installed
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    return shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return resolve_ffmpeg() is not None
