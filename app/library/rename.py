"""Filename templating and rename plan/apply/undo.

Tokens are substituted with an explicit allow-list. ``str.format`` is
deliberately not used: it would allow attribute access injection such as
``{0.__class__}``.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from ..db import Database
from .safety import UnsafePath, resolve_root, resolve_within

DEFAULT_TEMPLATE = "{artist}/{album}/{track:02d} - {title}"

TOKENS = ("artist", "albumartist", "album", "title", "track", "disc", "year", "ext")
_TOKEN_RE = re.compile(r"\{([a-zA-Z_]+)(?::([^{}]*))?\}")
_SPEC_RE = re.compile(r"^0?\d{0,2}d?$")
_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_NAME = 180


class TemplateError(ValueError):
    pass


def _sanitize_value(value: Any) -> str:
    """Make a single field safe *inside* one path component.

    Separators are replaced here so a tag like ``AC/DC`` cannot silently
    create an extra directory level.
    """
    return _ILLEGAL_RE.sub("_", str(value))


def _format_value(value: Any, spec: str | None) -> str:
    if not spec:
        return "" if value is None else _sanitize_value(value)
    if not _SPEC_RE.match(spec):
        raise TemplateError(f"invalid format specifier ':{spec}'")
    if value in (None, ""):
        return ""
    if "d" in spec:
        try:
            number = int(str(value).split("/")[0])
        except (TypeError, ValueError):
            return _sanitize_value(value)
        return format(number, spec)
    return _sanitize_value(format(str(value), spec))


def render(template: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1).lower()
        if name not in TOKENS:
            raise TemplateError(f"unknown token {{{name}}}")
        return _format_value(context.get(name), match.group(2))

    return _TOKEN_RE.sub(replace, template)


def sanitize_component(value: str) -> str:
    value = _ILLEGAL_RE.sub("_", value)
    value = re.sub(r"\s+", " ", value).strip().strip(".")
    return value[:MAX_NAME]


def build_target(template: str, context: dict[str, Any]) -> str:
    rendered = render(template, context).replace("\\", "/")
    parts = [sanitize_component(part) for part in rendered.split("/")]
    parts = [part for part in parts if part]
    if not parts:
        raise TemplateError("template produced an empty filename")
    return "/".join(parts)


def plan(
    db: Database,
    root: Path | str,
    track_ids: list[str],
    template: str,
) -> list[dict[str, Any]]:
    base = resolve_root(root)
    items: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    for track_id in dict.fromkeys(track_ids):
        row = db.get_track(track_id)
        if row is None:
            continue
        ext = (row.get("ext") or "").lstrip(".").lower()
        context = {**row, "ext": ext}
        try:
            target = build_target(template or DEFAULT_TEMPLATE, context)
        except TemplateError as exc:
            items.append(
                {
                    "id": track_id,
                    "src_rel": row["relpath"],
                    "dst_rel": row["relpath"],
                    "title": row.get("title") or row.get("filename"),
                    "status": "invalid",
                    "reason": str(exc),
                }
            )
            continue
        if ext and not target.lower().endswith(f".{ext}"):
            target = f"{target}.{ext}"
            target = "/".join(sanitize_component(part) for part in target.split("/"))

        item = {
            "id": track_id,
            "src_rel": row["relpath"],
            "dst_rel": target,
            "title": row.get("title") or row.get("filename"),
            "status": "ok",
            "reason": "",
        }
        if target == row["relpath"]:
            item["status"] = "unchanged"
        items.append(item)
        counts[target] = counts.get(target, 0) + 1

    for item in items:
        if item["status"] != "ok":
            continue
        if counts[item["dst_rel"]] > 1:
            item["status"] = "conflict"
            item["reason"] = "another track maps to the same target"
            continue
        try:
            target_path = resolve_within(base, item["dst_rel"])
        except UnsafePath as exc:
            item["status"] = "conflict"
            item["reason"] = str(exc)
            continue
        if target_path.exists():
            item["status"] = "conflict"
            item["reason"] = "target already exists"
    return items


def apply_plan(
    db: Database,
    root: Path | str,
    track_ids: list[str],
    template: str,
) -> dict[str, Any]:
    base = resolve_root(root)
    items = plan(db, base, track_ids, template)
    batch = uuid.uuid4().hex[:12]
    moved: list[dict[str, str]] = []
    skipped: list[dict[str, Any]] = []

    for item in items:
        if item["status"] != "ok":
            skipped.append(item)
            continue
        source = resolve_within(base, item["src_rel"])
        target = resolve_within(base, item["dst_rel"])
        if not source.is_file():
            skipped.append({**item, "status": "missing", "reason": "source file is gone"})
            continue
        if target.exists() and target != source:
            skipped.append({**item, "status": "conflict", "reason": "target already exists"})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)
        db.rename_track(item["id"], item["dst_rel"], Path(item["dst_rel"]).name)
        moved.append({"src": item["src_rel"], "dst": item["dst_rel"]})

    if moved:
        db.log_op("rename", moved, batch)
    return {"moved": len(moved), "skipped": skipped, "batch": batch}


def undo_last_rename(db: Database, root: Path | str) -> dict[str, Any]:
    base = resolve_root(root)
    row = db.last_op("rename")
    if row is None:
        return {"reverted": 0, "reason": "nothing to undo"}

    reverted: list[dict[str, str]] = []
    for entry in reversed(row["payload"] or []):
        try:
            target = resolve_within(base, entry["dst"])
            source = resolve_within(base, entry["src"])
        except UnsafePath:
            continue
        if not target.is_file() or source.exists():
            continue
        source.parent.mkdir(parents=True, exist_ok=True)
        target.replace(source)
        track = db.one("SELECT id FROM tracks WHERE relpath = ?", (entry["dst"],))
        if track:
            db.rename_track(track["id"], entry["src"], Path(entry["src"]).name)
        reverted.append(entry)

    db.delete_op(row["id"])
    return {"reverted": len(reverted), "batch": row["batch"]}


def undo_last_tag_edit(db: Database, root: Path | str) -> dict[str, Any]:
    from .tags import write_tags

    base = resolve_root(root)
    row = db.last_op("tags")
    if row is None:
        return {"reverted": 0, "reason": "nothing to undo"}
    payload = row["payload"] or {}
    relpath = payload.get("relpath")
    before = payload.get("before") or {}
    if not relpath:
        db.delete_op(row["id"])
        return {"reverted": 0}
    try:
        path = resolve_within(base, relpath)
    except UnsafePath:
        db.delete_op(row["id"])
        return {"reverted": 0}
    if path.is_file():
        write_tags(path, before)
        track = db.one("SELECT id FROM tracks WHERE relpath = ?", (relpath,))
        if track:
            db.update_track_tags(track["id"], before)
    db.delete_op(row["id"])
    return {"reverted": 1}
