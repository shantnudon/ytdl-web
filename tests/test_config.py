"""Config surface tests: env var names are part of the public contract.

The Docker image sets APP_HOST/APP_PORT, so a rename here silently breaks every
container that maps a port.
"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings


def test_app_host_and_port_come_from_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    monkeypatch.setenv("APP_PORT", "9999")
    monkeypatch.setenv("YTDLWEB_DATA_DIR", str(tmp_path / "data"))
    settings = Settings().normalize()
    assert settings.app_host == "0.0.0.0"
    assert settings.app_port == 9999


def test_documented_paths_resolve(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DOWNLOAD_DIR", str(tmp_path / "dl"))
    monkeypatch.setenv("LIBRARY_DIR", str(tmp_path / "music"))
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "cfg"))
    settings = Settings().normalize()
    assert settings.download_dir == (tmp_path / "dl").resolve()
    assert settings.library_dir == (tmp_path / "music").resolve()
    assert settings.config_dir == (tmp_path / "cfg").resolve()
    assert settings.db_path == (tmp_path / "cfg" / "ytdlweb.db").resolve()


def test_defaults_are_localhost_only(monkeypatch, tmp_path: Path):
    for name in ("APP_HOST", "APP_PORT", "ALLOW_WRITE", "APP_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("YTDLWEB_DATA_DIR", str(tmp_path))
    settings = Settings().normalize()
    assert settings.app_host == "127.0.0.1"
    assert settings.app_port == 8080
    assert settings.allow_write is False
    assert settings.app_token is None
