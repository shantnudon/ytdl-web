from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..cli import update_extractors
from ..core.options import DEFAULT_PRESET, normalize_preset
from ..deps import Db, SettingsDep
from ..library.rename import DEFAULT_TEMPLATE, TOKENS, TemplateError, build_target

router = APIRouter(prefix="/api/prefs", tags=["prefs"])

MAX_COOKIES_BYTES = 2 * 1024 * 1024

_SAMPLE_TRACK = {
    "artist": "Artist",
    "albumartist": "Artist",
    "album": "Album",
    "title": "Title",
    "track": "1",
    "disc": "1",
    "year": "2000",
    "ext": "mp3",
}


class PrefsIn(BaseModel):
    default_preset: dict[str, Any] = Field(default_factory=dict)
    default_template: str = Field(default=DEFAULT_TEMPLATE, max_length=300)


def _stored(db: Db) -> dict[str, Any]:
    preset = dict(DEFAULT_PRESET)
    raw = db.kv_get("default_preset")
    if raw:
        try:
            preset = normalize_preset(json.loads(raw))
        except json.JSONDecodeError:
            preset = dict(DEFAULT_PRESET)
    template = db.kv_get("default_template") or DEFAULT_TEMPLATE
    return {"default_preset": preset, "default_template": template}


@router.get("")
def get_prefs(settings: SettingsDep, db: Db) -> dict[str, Any]:
    return {
        **_stored(db),
        "template_tokens": list(TOKENS),
        "allow_write": settings.allow_write,
        "has_cookies": bool(settings.cookies_file and settings.cookies_file.is_file()),
        "cookies_path": str(settings.cookies_file) if settings.cookies_file else None,
    }


@router.put("")
def save_prefs(payload: PrefsIn, settings: SettingsDep, db: Db) -> dict[str, Any]:
    preset = normalize_preset(payload.default_preset)
    template = payload.default_template.strip() or DEFAULT_TEMPLATE
    try:
        build_target(template, _SAMPLE_TRACK)
    except TemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.kv_set("default_preset", json.dumps(preset))
    db.kv_set("default_template", template)
    return get_prefs(settings, db)


@router.post("/cookies")
async def upload_cookies(file: UploadFile, settings: SettingsDep) -> dict[str, Any]:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > MAX_COOKIES_BYTES:
        raise HTTPException(status_code=413, detail="cookies file is too large")
    target = settings.config_dir / "cookies.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.chmod(0o600)
    settings.cookies_file = target
    return {"ok": True, "path": str(target)}


@router.delete("/cookies")
def delete_cookies(settings: SettingsDep) -> dict[str, Any]:
    target = settings.cookies_file or (settings.config_dir / "cookies.txt")
    target.unlink(missing_ok=True)
    settings.cookies_file = None
    return {"ok": True}


@router.post("/update-extractors")
async def update_extractor_plugin(settings: SettingsDep) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(update_extractors, settings.plugin_dir)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"update failed: {exc}"[:400]) from exc
