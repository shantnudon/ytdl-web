"""Audio tag reading/writing via mutagen. Reads are best-effort, writes atomic."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3
from mutagen.mp4 import MP4, MP4Cover

from .safety import atomic_write

AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".ogg", ".opus", ".wav"}
WRITABLE_EXTS = {".mp3", ".m4a", ".flac", ".ogg", ".opus"}

# UI field -> mutagen "easy" key
EASY_FIELDS = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "albumartist": "albumartist",
    "year": "date",
    "track": "tracknumber",
    "disc": "discnumber",
    "genre": "genre",
    "comment": "comment",
}

MAX_ART_BYTES = 8 * 1024 * 1024


def empty_meta() -> dict[str, Any]:
    meta: dict[str, Any] = {field: "" for field in EASY_FIELDS}
    meta.update({"duration": 0.0, "bitrate": 0, "has_art": False})
    return meta


def probe_file(path: Path) -> dict[str, Any]:
    meta = empty_meta()
    try:
        audio = mutagen.File(str(path), easy=True)
    except Exception:
        return meta
    if audio is None:
        return meta
    for field, key in EASY_FIELDS.items():
        try:
            values = audio.get(key)
        except Exception:
            continue
        if values:
            meta[field] = str(values[0])
    info = getattr(audio, "info", None)
    if info is not None:
        meta["duration"] = float(getattr(info, "length", 0) or 0)
        meta["bitrate"] = int(getattr(info, "bitrate", 0) or 0)
    meta["has_art"] = has_art(path)
    return meta


def has_art(path: Path) -> bool:
    suffix = path.suffix.lower()
    try:
        if suffix == ".mp3":
            return bool(ID3(str(path)).getall("APIC"))
        if suffix in (".m4a", ".m4b", ".mp4"):
            tags = MP4(str(path)).tags
            return bool(tags and tags.get("covr"))
        if suffix == ".flac":
            return bool(FLAC(str(path)).pictures)
        audio = mutagen.File(str(path))
        return bool(getattr(audio, "pictures", None))
    except Exception:
        return False


def write_tags(path: Path, updates: dict[str, Any]) -> dict[str, Any]:
    """Apply tag updates atomically. Returns the metadata as it was before."""
    if path.suffix.lower() not in WRITABLE_EXTS:
        raise ValueError(f"tags are not writable for {path.suffix} files")
    before = probe_file(path)

    with atomic_write(path) as tmp:
        shutil.copy2(path, tmp)
        try:
            audio = mutagen.File(str(tmp), easy=True)
        except Exception as exc:
            raise ValueError(f"cannot parse audio file: {exc}") from exc
        if audio is None:
            raise ValueError("unsupported audio file")
        for field, key in EASY_FIELDS.items():
            if field not in updates:
                continue
            value = updates[field]
            if value is None or str(value).strip() == "":
                if audio.get(key):
                    del audio[key]
            else:
                audio[key] = [str(value).strip()]
        audio.save()

    return before


def set_art(path: Path, data: bytes, mime: str = "") -> None:
    if path.suffix.lower() not in WRITABLE_EXTS:
        raise ValueError("cover art is not supported for this format")
    if len(data) > MAX_ART_BYTES:
        raise ValueError("cover image is too large (max 8MB)")
    mime = mime or sniff_image(data)

    with atomic_write(path) as tmp:
        shutil.copy2(path, tmp)
        suffix = path.suffix.lower()
        if suffix == ".mp3":
            try:
                tags = ID3(str(tmp))
            except Exception:
                tags = ID3()
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data))
            tags.save(str(tmp))
        elif suffix in (".m4a", ".m4b"):
            audio = MP4(str(tmp))
            image_format = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
            audio["covr"] = [MP4Cover(data, imageformat=image_format)]
            audio.save()
        elif suffix == ".flac":
            audio = FLAC(str(tmp))
            picture = Picture()
            picture.data = data
            picture.mime = mime
            picture.type = 3
            picture.desc = "Cover"
            audio.clear_pictures()
            audio.add_picture(picture)
            audio.save()
        else:
            raise ValueError("cover art is not supported for this format")


def remove_art(path: Path) -> None:
    if path.suffix.lower() not in WRITABLE_EXTS:
        raise ValueError("cover art is not supported for this format")
    with atomic_write(path) as tmp:
        shutil.copy2(path, tmp)
        suffix = path.suffix.lower()
        if suffix == ".mp3":
            tags = ID3(str(tmp))
            tags.delall("APIC")
            tags.save(str(tmp))
        elif suffix in (".m4a", ".m4b"):
            audio = MP4(str(tmp))
            audio.pop("covr", None)
            audio.save()
        elif suffix == ".flac":
            audio = FLAC(str(tmp))
            audio.clear_pictures()
            audio.save()


def sniff_image(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"
