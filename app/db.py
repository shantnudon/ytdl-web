"""SQLite persistence layer.

A single connection guarded by a re-entrant lock is plenty for a single-user
self-hosted tool: writes are tiny and WAL mode keeps readers unblocked.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    title       TEXT,
    preset      TEXT NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'queued',
    progress    REAL NOT NULL DEFAULT 0,
    speed       REAL,
    eta         INTEGER,
    outpath     TEXT,
    error       TEXT,
    log         TEXT,
    created_at  REAL NOT NULL,
    started_at  REAL,
    finished_at REAL
);

CREATE TABLE IF NOT EXISTS tracks (
    id          TEXT PRIMARY KEY,
    relpath     TEXT NOT NULL UNIQUE,
    filename    TEXT NOT NULL,
    title       TEXT DEFAULT '',
    artist      TEXT DEFAULT '',
    album       TEXT DEFAULT '',
    albumartist TEXT DEFAULT '',
    year        TEXT DEFAULT '',
    track       TEXT DEFAULT '',
    disc        TEXT DEFAULT '',
    genre       TEXT DEFAULT '',
    comment     TEXT DEFAULT '',
    ext         TEXT DEFAULT '',
    size        INTEGER DEFAULT 0,
    mtime       REAL DEFAULT 0,
    duration    REAL DEFAULT 0,
    bitrate     INTEGER DEFAULT 0,
    has_art     INTEGER DEFAULT 0,
    search      TEXT DEFAULT '',
    scanned_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist);
CREATE INDEX IF NOT EXISTS idx_tracks_search ON tracks(search);

CREATE TABLE IF NOT EXISTS op_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,
    batch      TEXT,
    payload    TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);
"""

JOB_FIELDS = {
    "title",
    "preset",
    "status",
    "progress",
    "speed",
    "eta",
    "outpath",
    "error",
    "log",
    "started_at",
    "finished_at",
}

TRACK_FIELDS = (
    "id",
    "relpath",
    "filename",
    "title",
    "artist",
    "album",
    "albumartist",
    "year",
    "track",
    "disc",
    "genre",
    "comment",
    "ext",
    "size",
    "mtime",
    "duration",
    "bitrate",
    "has_art",
    "search",
    "scanned_at",
)


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # -- primitives ---------------------------------------------------------
    def execute(self, sql: str, params: tuple = ()) -> int:
        """Run a statement, return affected row count."""
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.rowcount

    def insert(self, sql: str, params: tuple = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return int(cur.lastrowid or 0)

    def executemany(self, sql: str, rows: Iterable[tuple]) -> None:
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- jobs ---------------------------------------------------------------
    def add_job(self, job_id: str, url: str, preset: dict, title: str | None = None) -> None:
        self.insert(
            "INSERT INTO jobs (id, url, title, preset, status, created_at) VALUES (?,?,?,?,?,?)",
            (job_id, url, title, json.dumps(preset), "queued", time.time()),
        )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.one("SELECT * FROM jobs WHERE id = ?", (job_id,))

    def list_jobs(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))

    def update_job(self, job_id: str, **fields: Any) -> None:
        data = {k: v for k, v in fields.items() if k in JOB_FIELDS}
        if not data:
            return
        assignments = ", ".join(f"{key} = ?" for key in data)
        self.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*data.values(), job_id))

    def delete_job(self, job_id: str) -> None:
        self.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def mark_interrupted(self) -> int:
        return self.execute(
            "UPDATE jobs SET status = 'interrupted', finished_at = ? "
            "WHERE status IN ('running', 'postprocessing')",
            (time.time(),),
        )

    def clear_finished(self) -> int:
        return self.execute("DELETE FROM jobs WHERE status IN ('done', 'failed', 'canceled')")

    # -- library ------------------------------------------------------------
    def upsert_track(self, row: dict[str, Any]) -> None:
        values = {key: row.get(key) for key in TRACK_FIELDS}
        values["has_art"] = 1 if row.get("has_art") else 0
        placeholders = ", ".join("?" for _ in TRACK_FIELDS)
        updates = ", ".join(f"{key} = excluded.{key}" for key in TRACK_FIELDS if key != "id")
        self.execute(
            f"INSERT INTO tracks ({', '.join(TRACK_FIELDS)}) VALUES ({placeholders}) "
            f"ON CONFLICT(relpath) DO UPDATE SET {updates}",
            tuple(values[key] for key in TRACK_FIELDS),
        )

    def get_track(self, track_id: str) -> dict[str, Any] | None:
        return self.one("SELECT * FROM tracks WHERE id = ?", (track_id,))

    def count_tracks(self, needle: str = "") -> int:
        if needle:
            row = self.one(
                "SELECT COUNT(*) AS n FROM tracks WHERE search LIKE ?", (f"%{needle.lower()}%",)
            )
        else:
            row = self.one("SELECT COUNT(*) AS n FROM tracks")
        return int(row["n"]) if row else 0

    def list_tracks(
        self, needle: str = "", limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        if needle:
            return self.query(
                "SELECT * FROM tracks WHERE search LIKE ? ORDER BY artist, album, track "
                "LIMIT ? OFFSET ?",
                (f"%{needle.lower()}%", limit, offset),
            )
        return self.query(
            "SELECT * FROM tracks ORDER BY artist, album, track LIMIT ? OFFSET ?",
            (limit, offset),
        )

    def all_relpaths(self) -> list[str]:
        return [row["relpath"] for row in self.query("SELECT relpath FROM tracks")]

    def delete_tracks(self, relpaths: Iterable[str]) -> int:
        relpaths = list(relpaths)
        removed = 0
        for chunk_start in range(0, len(relpaths), 200):
            chunk = relpaths[chunk_start : chunk_start + 200]
            marks = ", ".join("?" for _ in chunk)
            removed += self.execute(f"DELETE FROM tracks WHERE relpath IN ({marks})", tuple(chunk))
        return removed

    def rename_track(self, track_id: str, relpath: str, filename: str) -> None:
        self.execute(
            "UPDATE tracks SET relpath = ?, filename = ? WHERE id = ?",
            (relpath, filename, track_id),
        )

    def update_track_tags(self, track_id: str, tags: dict[str, Any]) -> None:
        allowed = {
            "title",
            "artist",
            "album",
            "albumartist",
            "year",
            "track",
            "disc",
            "genre",
            "comment",
        }
        data = {k: v for k, v in tags.items() if k in allowed}
        if not data:
            return
        search = self.get_track(track_id)
        if search is None:
            return
        merged = {**search, **data}
        data["search"] = search_blob(merged)
        assignments = ", ".join(f"{key} = ?" for key in data)
        self.execute(f"UPDATE tracks SET {assignments} WHERE id = ?", (*data.values(), track_id))

    def set_has_art(self, track_id: str, has_art: bool) -> None:
        self.execute("UPDATE tracks SET has_art = ? WHERE id = ?", (1 if has_art else 0, track_id))

    # -- op log -------------------------------------------------------------
    def log_op(self, kind: str, payload: Any, batch: str | None = None) -> int:
        return self.insert(
            "INSERT INTO op_log (kind, batch, payload, created_at) VALUES (?,?,?,?)",
            (kind, batch, json.dumps(payload), time.time()),
        )

    def last_op(self, kind: str) -> dict[str, Any] | None:
        row = self.one("SELECT * FROM op_log WHERE kind = ? ORDER BY id DESC LIMIT 1", (kind,))
        if row:
            row["payload"] = json.loads(row["payload"])
        return row

    def delete_op(self, op_id: int) -> None:
        self.execute("DELETE FROM op_log WHERE id = ?", (op_id,))

    # -- kv -----------------------------------------------------------------
    def kv_get(self, key: str) -> str | None:
        row = self.one("SELECT v FROM kv WHERE k = ?", (key,))
        return row["v"] if row else None

    def kv_set(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
            (key, value),
        )


def search_blob(row: dict[str, Any]) -> str:
    parts = [
        row.get("title") or "",
        row.get("artist") or "",
        row.get("album") or "",
        row.get("albumartist") or "",
        row.get("genre") or "",
        row.get("filename") or "",
        row.get("year") or "",
    ]
    return " ".join(str(part) for part in parts).lower()
