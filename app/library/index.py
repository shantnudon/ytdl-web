"""Library indexer: walks the mounted music directory into SQLite."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..db import Database, search_blob
from .safety import resolve_root
from .tags import AUDIO_EXTS, probe_file

log = logging.getLogger(__name__)

MAX_FILES = 20000


def scan(
    root: Path | str,
    db: Database,
    *,
    max_files: int = MAX_FILES,
    on_progress: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    base = resolve_root(root)
    seen: set[str] = set()
    added = updated = errors = 0

    for path in sorted(base.rglob("*")):
        if len(seen) >= max_files:
            log.warning("library scan hit the %s file limit", max_files)
            break
        try:
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTS:
                continue
            if path.name.startswith("."):
                continue
            resolved = path.resolve(strict=True)
        except OSError:
            continue
        if base not in resolved.parents:
            continue  # symlink pointing outside the root

        relpath = resolved.relative_to(base).as_posix()
        seen.add(relpath)
        try:
            stat = resolved.stat()
        except OSError:
            continue

        existing = db.one("SELECT id, mtime, size FROM tracks WHERE relpath = ?", (relpath,))
        if (
            existing
            and abs(float(existing["mtime"] or 0) - stat.st_mtime) < 1.0
            and int(existing["size"] or 0) == stat.st_size
        ):
            continue

        try:
            meta = probe_file(resolved)
        except Exception:  # noqa: BLE001
            errors += 1
            continue

        row = {
            "id": existing["id"] if existing else uuid.uuid4().hex[:16],
            "relpath": relpath,
            "filename": resolved.name,
            **meta,
            "ext": resolved.suffix.lower(),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "scanned_at": time.time(),
        }
        row["search"] = search_blob(row)
        db.upsert_track(row)
        if existing:
            updated += 1
        else:
            added += 1
        if on_progress and (added + updated) % 100 == 0:
            on_progress(added + updated)

    stale = set(db.all_relpaths()) - seen
    removed = db.delete_tracks(stale) if stale else 0
    return {
        "added": added,
        "updated": updated,
        "removed": removed,
        "errors": errors,
        "total": len(seen),
        "root": str(base),
    }
