from __future__ import annotations

from pathlib import Path

import pytest

from app.db import Database
from app.library import rename


def _seed(db: Database, root: Path, relpath: str, **tags) -> str:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not really audio")
    track_id = f"id-{abs(hash(relpath)) % 10**8}"
    db.upsert_track(
        {
            "id": track_id,
            "relpath": relpath,
            "filename": path.name,
            "ext": path.suffix,
            "size": path.stat().st_size,
            "mtime": path.stat().st_mtime,
            "search": "",
            **tags,
        }
    )
    return track_id


@pytest.mark.parametrize(
    "template,context,expected",
    [
        (
            "{artist}/{album}/{track:02d} - {title}",
            {"artist": "A", "album": "B", "track": "3", "title": "T"},
            "A/B/03 - T",
        ),
        ("{artist} - {title}", {"artist": "AC/DC", "title": "TNT"}, "AC_DC - TNT"),
        ("{year}/{title}", {"year": "1999", "title": "a:b"}, "1999/a_b"),
        ("{track:02d}", {"track": "7/12"}, "07"),
        ("{title}", {"title": "  spaced  "}, "spaced"),
    ],
)
def test_build_target(template, context, expected):
    assert rename.build_target(template, context) == expected


def test_unknown_token_is_rejected():
    with pytest.raises(rename.TemplateError):
        rename.build_target("{nope}", {})


def test_format_spec_injection_is_rejected():
    with pytest.raises(rename.TemplateError):
        rename.build_target("{title:>1000000}", {"title": "x"})


def test_plan_marks_conflicts_and_unchanged(tmp_path: Path, db: Database):
    root = tmp_path / "library"
    root.mkdir()
    first = _seed(db, root, "old/first.mp3", title="Same", artist="A", album="L")
    second = _seed(db, root, "old/second.mp3", title="Same", artist="A", album="L")
    same = _seed(db, root, "A/L/Keep.mp3", title="Keep", artist="A", album="L")

    items = rename.plan(db, root, [first, second, same], "{artist}/{album}/{title}")
    statuses = {item["id"]: item["status"] for item in items}
    assert statuses[first] == "conflict"
    assert statuses[second] == "conflict"
    assert statuses[same] == "unchanged"


def test_apply_and_undo(tmp_path: Path, db: Database):
    root = tmp_path / "library"
    root.mkdir()
    track = _seed(db, root, "raw/track.mp3", title="Song", artist="Band", album="Record", track="4")

    result = rename.apply_plan(db, root, [track], "{artist}/{album}/{track:02d} - {title}")
    assert result["moved"] == 1
    moved = root / "Band" / "Record" / "04 - Song.mp3"
    assert moved.is_file()
    assert db.get_track(track)["relpath"] == "Band/Record/04 - Song.mp3"

    undo = rename.undo_last_rename(db, root)
    assert undo["reverted"] == 1
    assert (root / "raw" / "track.mp3").is_file()
    assert db.get_track(track)["relpath"] == "raw/track.mp3"


def test_apply_never_overwrites_existing_file(tmp_path: Path, db: Database):
    root = tmp_path / "library"
    root.mkdir()
    track = _seed(db, root, "raw/track.mp3", title="Song", artist="Band", album="Record")
    occupied = root / "Band" / "Record" / "Song.mp3"
    occupied.parent.mkdir(parents=True)
    occupied.write_bytes(b"important")

    result = rename.apply_plan(db, root, [track], "{artist}/{album}/{title}")
    assert result["moved"] == 0
    assert result["skipped"][0]["status"] == "conflict"
    assert occupied.read_bytes() == b"important"


def test_plan_sanitizes_traversal_from_tags(tmp_path: Path, db: Database):
    root = tmp_path / "library"
    root.mkdir()
    track = _seed(db, root, "raw/track.mp3", title="../../evil", artist="..")
    items = rename.plan(db, root, [track], "{title}")
    assert items[0]["status"] == "ok"
    dst = items[0]["dst_rel"]
    assert ".." not in dst.split("/")
    assert not dst.startswith("/")
    from app.library.safety import resolve_within

    assert root.resolve() in resolve_within(root, dst).parents
