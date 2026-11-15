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
