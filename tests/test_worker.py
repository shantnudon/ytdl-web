from __future__ import annotations

import threading

import pytest

from app._ytdlp import DownloadCancelled
from app.core.worker import DownloadManager
from app.events import Broker


@pytest.fixture
def manager(db, settings) -> DownloadManager:
    return DownloadManager(db, Broker(), settings)


def test_progress_hook_captures_title(manager, db):
    db.add_job("job1", "https://example.com/x", {})
    hook = manager._progress_hook("job1", threading.Event())
    hook(
        {
            "status": "downloading",
            "downloaded_bytes": 5,
            "total_bytes": 10,
            "info_dict": {"title": "Real Title"},
        }
    )
    assert db.get_job("job1")["title"] == "Real Title"
    assert db.get_job("job1")["progress"] == 50.0


def test_progress_hook_only_sets_title_once(manager, db):
    db.add_job("job2", "https://example.com/x", {})
    hook = manager._progress_hook("job2", threading.Event())
    hook({"status": "downloading", "info_dict": {"title": "First"}})
    hook({"status": "downloading", "info_dict": {"title": "Second"}})
    assert db.get_job("job2")["title"] == "First"


def test_progress_hook_raises_when_canceled(manager):
    cancel = threading.Event()
    cancel.set()
    hook = manager._progress_hook("job3", cancel)
    with pytest.raises(DownloadCancelled):
        hook({"status": "downloading"})


def test_stage_marks_postprocessing(manager, db):
    db.add_job("job4", "https://example.com/x", {})
    hook = manager._progress_hook("job4", threading.Event())
    hook({"status": "finished"})
    row = db.get_job("job4")
    assert row["status"] == "postprocessing"
    assert row["progress"] == 100.0


def test_post_hook_keeps_only_finished_media(manager, tmp_path):
    resolved = []
    hook = manager._post_hook(resolved)
    webm = tmp_path / "a.webm"
    mp3 = tmp_path / "a.mp3"
    jpg = tmp_path / "a.jpg"
    for path in (webm, mp3, jpg):
        path.write_bytes(b"x")

    hook({"status": "started", "info_dict": {"filepath": str(webm)}})
    hook({"status": "finished", "info_dict": {"filepath": str(jpg)}})
    hook({"status": "finished", "info_dict": {"filepath": str(webm)}})
    hook({"status": "finished", "info_dict": {"filepath": str(webm)}})
    hook({"status": "finished", "info_dict": {"filepath": str(mp3)}})

    assert resolved == [str(webm), str(mp3)]


def test_existing_media_filters_missing_and_non_media(tmp_path):
    from app.core.worker import existing_media

    mp3 = tmp_path / "song.mp3"
    jpg = tmp_path / "cover.jpg"
    mp3.write_bytes(b"x")
    jpg.write_bytes(b"x")
    gone = str(tmp_path / "gone.webm")

    assert existing_media([gone, str(jpg), str(mp3), str(mp3), "", None]) == [str(mp3)]


def test_repair_outpaths_recovers_converted_file(db, tmp_path):
    from app.core.worker import repair_outpaths

    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"x")
    db.add_job("job9", "https://example.com/x", {})
    db.update_job("job9", status="done", outpath=str(tmp_path / "song.webm"))

    assert repair_outpaths(db, tmp_path) == 1
    assert db.get_job("job9")["outpath"] == str(mp3.resolve())


def test_repair_outpaths_ignores_missing_and_outside_files(db, tmp_path):
    from app.core.worker import repair_outpaths

    outside = tmp_path.parent / "outside.mp3"
    outside.write_bytes(b"x")
    downloads = tmp_path / "downloads"
    downloads.mkdir()

    db.add_job("job10", "https://example.com/x", {})
    db.update_job("job10", status="done", outpath=str(downloads / "gone.webm"))
    db.add_job("job11", "https://example.com/y", {})
    db.update_job("job11", status="done", outpath=str(tmp_path / "outside.webm"))

    assert repair_outpaths(db, downloads) == 0
