"""Download orchestration: a small worker pool around blocking yt-dlp calls."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from .. import _ytdlp as ytdlp
from .._ytdlp import DownloadCancelled
from ..config import Settings
from ..db import Database
from ..events import Broker
from .ffmpeg import resolve_ffmpeg
from .options import build_opts, normalize_preset

log = logging.getLogger(__name__)

PROGRESS_INTERVAL = 0.25  # seconds between SSE frames per job
LOG_TAIL = 8000
SKIP_STATUSES = {"running", "postprocessing", "done", "canceled"}


def _short(text: str, limit: int = 600) -> str:
    text = " ".join(str(text).split())
    return text[:limit]


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _collect_paths(info: Any) -> list[str]:
    if not info:
        return []
    if info.get("_type") == "playlist":
        paths: list[str] = []
        for entry in info.get("entries") or []:
            paths.extend(_collect_paths(entry))
        return paths
    paths = []
    for download in info.get("requested_downloads") or []:
        path = download.get("filepath")
        if path:
            paths.append(path)
    if not paths:
        path = info.get("filepath") or info.get("_filename")
        if path:
            paths.append(path)
    return paths


class YtdlpLogger:
    """Routes yt-dlp's messages into the per-job log buffer."""

    def __init__(self, sink: Callable[[str], None]) -> None:
        self._sink = sink

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug]"):
            self._sink(msg)

    def info(self, msg: str) -> None:
        if msg.strip():
            self._sink(msg)

    def warning(self, msg: str) -> None:
        self._sink(f"WARNING: {msg}")

    def error(self, msg: str) -> None:
        self._sink(f"ERROR: {msg}")


class DownloadManager:
    def __init__(self, db: Database, broker: Broker, settings: Settings) -> None:
        self.db = db
        self.broker = broker
        self.settings = settings
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._cancels: dict[str, threading.Event] = {}
        self._last_push: dict[str, float] = {}
        self._logs: dict[str, list[str]] = {}

    # -- lifecycle ----------------------------------------------------------
    async def start(self) -> None:
        count = max(1, int(self.settings.max_concurrent))
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"download-worker-{index}")
            for index in range(count)
        ]

    async def stop(self) -> None:
        for event in list(self._cancels.values()):
            event.set()
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

    async def enqueue(self, job_id: str) -> None:
        await self._queue.put(job_id)

    def cancel(self, job_id: str) -> bool:
        event = self._cancels.get(job_id)
        if event is None:
            return False
        event.set()
        return True

    def is_running(self, job_id: str) -> bool:
        return job_id in self._cancels

    def running_count(self) -> int:
        return len(self._cancels)

    def emit_job(self, job_id: str) -> None:
        """Push the current job row to SSE subscribers."""
        self._emit(job_id)

    # -- worker -------------------------------------------------------------
    async def _worker(self, index: int) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._run(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - never kill the worker loop
                log.exception("unhandled error while running job %s", job_id)
                self.db.update_job(job_id, status="failed", error="internal error")
                self._emit(job_id)
            finally:
                self._queue.task_done()

    async def _run(self, job_id: str) -> None:
        job = self.db.get_job(job_id)
        if job is None or job["status"] in SKIP_STATUSES:
            return

        self.db.update_job(
            job_id,
            status="running",
            started_at=time.time(),
            progress=0.0,
            error=None,
            finished_at=None,
        )
        self._logs[job_id] = []
        self._emit(job_id)

        cancel = threading.Event()
        self._cancels[job_id] = cancel

        try:
            paths = await asyncio.to_thread(self._download, job, cancel)
        except asyncio.CancelledError:
            self.db.update_job(job_id, status="interrupted", finished_at=time.time())
            raise
        except Exception as exc:  # noqa: BLE001
            canceled = cancel.is_set() or isinstance(exc, DownloadCancelled)
            self.db.update_job(
                job_id,
                status="canceled" if canceled else "failed",
                error="" if canceled else _short(exc),
                finished_at=time.time(),
            )
        else:
            self.db.update_job(
                job_id,
                status="done",
                progress=100.0,
                speed=None,
                eta=0,
                outpath=paths[0] if paths else None,
                error=None,
                finished_at=time.time(),
            )
        finally:
            self._cancels.pop(job_id, None)
            self._last_push.pop(job_id, None)
            self._flush_log(job_id)
            self._emit(job_id)

    # -- yt-dlp plumbing ----------------------------------------------------
    def _download(self, job: dict[str, Any], cancel: threading.Event) -> list[str]:
        preset = normalize_preset(_as_dict(job.get("preset")))
        collected: list[str] = []
        job_id = job["id"]

        opts = build_opts(
            preset,
            download_dir=self.settings.download_dir,
            cookies_file=self.settings.cookies_file,
            ffmpeg_path=resolve_ffmpeg(),
            archive_path=self.settings.archive_path,
            progress_hooks=[self._progress_hook(job_id, cancel)],
            postprocessor_hooks=[self._post_hook(collected)],
            logger=YtdlpLogger(lambda line: self._log_line(job_id, line)),
        )

        ydl = ytdlp.make(opts)
        try:
            info = ydl.extract_info(job["url"], download=True)
        finally:
            with suppress(Exception):  # pragma: no cover
                ydl.close()

        paths = [path for path in collected if path]
        return paths or _collect_paths(info)

    def _progress_hook(self, job_id: str, cancel: threading.Event) -> Callable[[dict], None]:
        def hook(data: dict) -> None:
            if cancel.is_set():
                raise DownloadCancelled("canceled by user")
            status = data.get("status")
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                done = data.get("downloaded_bytes") or 0
                percent = (done / total * 100.0) if total else 0.0
                self._throttled_progress(
                    job_id,
                    percent=round(percent, 2),
                    speed=data.get("speed"),
                    eta=data.get("eta"),
                )
            elif status == "finished":
                self._stage(job_id, "postprocessing")

        return hook

    def _post_hook(self, collected: list[str]) -> Callable[[dict], None]:
        def hook(data: dict) -> None:
            info = data.get("info_dict") or {}
            path = info.get("filepath") or info.get("_filename")
            if path:
                collected.append(path)

        return hook

    # -- state + events -----------------------------------------------------
    def _throttled_progress(
        self, job_id: str, *, percent: float, speed: float | None, eta: int | None
    ) -> None:
        now = time.monotonic()
        if now - self._last_push.get(job_id, 0.0) < PROGRESS_INTERVAL:
            return
        self._last_push[job_id] = now
        self.db.update_job(job_id, progress=percent, speed=speed, eta=eta)
        self._emit(job_id)

    def _stage(self, job_id: str, status: str) -> None:
        self._last_push.pop(job_id, None)
        self.db.update_job(job_id, status=status, progress=100.0, speed=None)
        self._emit(job_id)

    def _log_line(self, job_id: str, line: str) -> None:
        buffer = self._logs.setdefault(job_id, [])
        buffer.append(line)
        if len(buffer) > 400:
            del buffer[:100]

    def _flush_log(self, job_id: str) -> None:
        lines = self._logs.pop(job_id, [])
        if lines:
            self.db.update_job(job_id, log="\n".join(lines)[-LOG_TAIL:])

    def _job_payload(self, job_id: str) -> dict[str, Any] | None:
        job = self.db.get_job(job_id)
        if job is None:
            return None
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
            "created_at": job["created_at"],
            "started_at": job["started_at"],
            "finished_at": job["finished_at"],
        }

    def _emit(self, job_id: str) -> None:
        payload = self._job_payload(job_id)
        if payload:
            self.broker.publish_threadsafe("job.updated", payload)
