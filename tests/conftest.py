from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from app.config import Settings
from app.db import Database
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    cfg = Settings(
        data_dir=tmp_path,
        download_dir=tmp_path / "downloads",
        library_dir=tmp_path / "library",
        config_dir=tmp_path / "config",
        static_dir=tmp_path / "static",
        app_password=None,
        allow_write=True,
        max_concurrent=1,
    ).normalize()
    cfg.ensure_dirs()
    return cfg


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Requested-With": "ytdlweb"}
    ) as http:
        yield http


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


@pytest.fixture(scope="session")
def ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


@pytest.fixture
def silent_mp3(tmp_path: Path, ffmpeg: str | None) -> Path:
    if not ffmpeg:
        pytest.skip("ffmpeg is not installed")
    path = tmp_path / "library" / "Artist" / "Album" / "01 - Track.mp3"
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            "1",
            "-q:a",
            "9",
            str(path),
        ],
        check=True,
    )
    return path


PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
    b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(scope="session")
def png_1px() -> bytes:
    return PNG_1PX
