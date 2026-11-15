from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

from ..cli import update_extractors
from ..core.options import DEFAULT_PRESET
from ..deps import SettingsDep
from ..library.rename import DEFAULT_TEMPLATE, TOKENS

router = APIRouter(prefix="/api/prefs", tags=["prefs"])

MAX_COOKIES_BYTES = 2 * 1024 * 1024


@router.get("")
def get_prefs(settings: SettingsDep) -> dict[str, Any]:
    return {
        "default_preset": DEFAULT_PRESET,
        "default_template": DEFAULT_TEMPLATE,
        "template_tokens": list(TOKENS),
        "allow_write": settings.allow_write,
        "has_cookies": bool(settings.cookies_file and settings.cookies_file.is_file()),
        "cookies_path": str(settings.cookies_file) if settings.cookies_file else None,
    }


@router.post("/cookies", dependencies=[])
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
