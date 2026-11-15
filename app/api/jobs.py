from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import _ytdlp as ytdlp
from ..core.options import normalize_preset
from ..deps import Db, Manager, SettingsDep

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
probe_router = APIRouter(prefix="/api", tags=["probe"])


class JobIn(BaseModel):
    url: str = Field(min_length=5, max_length=2048)
    preset: dict[str, Any] = Field(default_factory=dict)
    title: str | None = Field(default=None, max_length=300)


class ProbeIn(BaseModel):
    url: str = Field(min_length=5, max_length=2048)
    playlist_limit: int = Field(default=100, ge=1, le=500)


def _clean_url(raw: str) -> str:
    url = raw.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="only http(s) URLs are supported")
    return url


def job_dict(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if job is None:
        return None
    try:
        preset = json.loads(job.get("preset") or "{}")
    except json.JSONDecodeError:
        preset = {}
    return {
        "id": job["id"],
        "url": job["url"],
        "title": job["title"],
        "status": job["status"],
        "progress": round(float(job["progress"] or 0), 2),
        "speed": job["speed"],
        "eta": job["eta"],
        "outpath": job["outpath"],
        "error": job["error"],
        "log": job["log"],
        "preset": preset,
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
    }


@router.post("", status_code=201)
async def create_job(payload: JobIn, db: Db, manager: Manager) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    preset = normalize_preset(payload.preset)
    db.add_job(job_id, _clean_url(payload.url), preset, title=payload.title)
    await manager.enqueue(job_id)
    return job_dict(db.get_job(job_id)) or {}


@router.get("")
def list_jobs(db: Db, limit: int = 200) -> dict[str, Any]:
    limit = max(1, min(500, limit))
    return {"items": [job_dict(job) for job in db.list_jobs(limit)]}


@router.get("/{job_id}")
def get_job(job_id: str, db: Db) -> dict[str, Any]:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job_dict(job) or {}


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, db: Db, manager: Manager) -> dict[str, Any]:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] == "queued":
        db.update_job(job_id, status="canceled", finished_at=time.time())
    else:
        manager.cancel(job_id)
    manager.emit_job(job_id)
    return {"ok": True}


@router.post("/{job_id}/retry")
async def retry_job(job_id: str, db: Db, manager: Manager) -> dict[str, Any]:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if manager.is_running(job_id):
        raise HTTPException(status_code=409, detail="job is still running")
    db.update_job(
        job_id,
        status="queued",
        progress=0.0,
        speed=None,
        eta=None,
        error=None,
        started_at=None,
        finished_at=None,
    )
    manager.emit_job(job_id)
    await manager.enqueue(job_id)
    return job_dict(db.get_job(job_id)) or {}


@router.delete("/{job_id}")
def delete_job(job_id: str, db: Db, manager: Manager) -> dict[str, Any]:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    manager.cancel(job_id)
    db.delete_job(job_id)
    return {"ok": True}


@probe_router.post("/probe")
async def probe(payload: ProbeIn, settings: SettingsDep) -> dict[str, Any]:
    cookies = None
    if settings.cookies_file and settings.cookies_file.is_file():
        cookies = str(settings.cookies_file)
    try:
        return await asyncio.to_thread(
            ytdlp.probe,
            _clean_url(payload.url),
            playlist_limit=payload.playlist_limit,
            cookies_file=cookies,
        )
    except ytdlp.DownloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)[:400]) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"extractor error: {exc}"[:400]) from exc
