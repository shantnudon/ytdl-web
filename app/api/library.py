from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..config import Settings
from ..deps import BrokerDep, Db, SettingsDep, WriteGuard
from ..library import index, rename, tags
from ..library.safety import UnsafePath, resolve_within

router = APIRouter(prefix="/api/library", tags=["library"])


class TagsIn(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    artist: str | None = Field(default=None, max_length=300)
    album: str | None = Field(default=None, max_length=300)
    albumartist: str | None = Field(default=None, max_length=300)
    year: str | None = Field(default=None, max_length=16)
    track: str | None = Field(default=None, max_length=16)
    disc: str | None = Field(default=None, max_length=16)
    genre: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=1000)


class RenameIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=5000)
    template: str = Field(default=rename.DEFAULT_TEMPLATE, max_length=300)


def _track(db: Db, track_id: str) -> dict[str, Any]:
    row = db.get_track(track_id)
    if row is None:
        raise HTTPException(status_code=404, detail="track not found")
    return row


def _track_path(settings: Settings, row: dict[str, Any]):
    try:
        return resolve_within(settings.library_dir, row["relpath"])
    except UnsafePath as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_tracks(
    db: Db,
    q: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    needle = q.strip()[:200]
    limit = max(1, min(500, limit))
    offset = max(0, offset)
    return {
        "items": db.list_tracks(needle, limit, offset),
        "total": db.count_tracks(needle),
        "limit": limit,
        "offset": offset,
        "query": needle,
    }


@router.post("/scan")
async def scan_library(db: Db, settings: SettingsDep, broker: BrokerDep) -> dict[str, Any]:
    result = await asyncio.to_thread(index.scan, settings.library_dir, db)
    broker.publish("library.scanned", result)
    return result


@router.get("/template")
def get_template() -> dict[str, str]:
    return {"template": rename.DEFAULT_TEMPLATE, "tokens": list(rename.TOKENS)}


@router.post("/rename/preview")
def preview_rename(payload: RenameIn, db: Db, settings: SettingsDep) -> dict[str, Any]:
    try:
        items = rename.plan(db, settings.library_dir, payload.ids, payload.template)
    except rename.TemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": items, "ok": sum(1 for item in items if item["status"] == "ok")}


@router.post("/rename/apply", dependencies=[WriteGuard])
def apply_rename(payload: RenameIn, db: Db, settings: SettingsDep) -> dict[str, Any]:
    try:
        return rename.apply_plan(db, settings.library_dir, payload.ids, payload.template)
    except rename.TemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/undo/rename", dependencies=[WriteGuard])
def undo_rename(db: Db, settings: SettingsDep) -> dict[str, Any]:
    return rename.undo_last_rename(db, settings.library_dir)


@router.post("/undo/tags", dependencies=[WriteGuard])
def undo_tags(db: Db, settings: SettingsDep) -> dict[str, Any]:
    return rename.undo_last_tag_edit(db, settings.library_dir)


@router.get("/{track_id}")
def get_track(track_id: str, db: Db) -> dict[str, Any]:
    return _track(db, track_id)


@router.patch("/{track_id}/tags", dependencies=[WriteGuard])
def update_tags(
    track_id: str, payload: TagsIn, db: Db, settings: SettingsDep
) -> dict[str, Any]:
    row = _track(db, track_id)
    path = _track_path(settings, row)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return row
    try:
        before = tags.write_tags(path, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.log_op("tags", {"track_id": track_id, "relpath": row["relpath"], "before": before})
    db.update_track_tags(track_id, updates)
    return _track(db, track_id)


@router.put("/{track_id}/art", dependencies=[WriteGuard])
async def upload_art(
    track_id: str,
    db: Db,
    settings: SettingsDep,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    row = _track(db, track_id)
    path = _track_path(settings, row)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    try:
        tags.set_art(path, data, file.content_type or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.set_has_art(track_id, True)
    return _track(db, track_id)


@router.delete("/{track_id}/art", dependencies=[WriteGuard])
def delete_art(track_id: str, db: Db, settings: SettingsDep) -> dict[str, Any]:
    row = _track(db, track_id)
    path = _track_path(settings, row)
    try:
        tags.remove_art(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.set_has_art(track_id, False)
    return _track(db, track_id)


@router.post("/{track_id}/forget", dependencies=[Depends(_track), WriteGuard])
def forget_track(track_id: str, db: Db) -> dict[str, Any]:
    """Remove a track from the index without touching the file on disk."""
    db.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
    return {"ok": True, "forgotten_at": time.time()}
