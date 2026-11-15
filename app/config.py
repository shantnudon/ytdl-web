from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    env = os.environ.get("YTDLWEB_DATA_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".local" / "share" / "ytdlweb"


class Settings(BaseSettings):
    """Runtime configuration. Every field maps to an UPPER_CASE env var."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_token: str | None = None

    app_host: str = "127.0.0.1"
    app_port: int = 8080
    log_level: str = "info"

    data_dir: Path = Field(default_factory=_default_data_dir)
    download_dir: Path | None = None
    library_dir: Path | None = None
    config_dir: Path | None = None
    static_dir: Path | None = None

    allow_write: bool = False
    max_concurrent: int = 3
    ffmpeg_path: str | None = None
    cookies_file: Path | None = None

    def normalize(self) -> Settings:
        def resolve(value: Path | str) -> Path:
            return Path(value).expanduser().resolve()

        self.data_dir = resolve(self.data_dir)
        self.download_dir = resolve(self.download_dir or self.data_dir / "downloads")
        self.library_dir = resolve(self.library_dir or self.data_dir / "library")
        self.config_dir = resolve(self.config_dir or self.data_dir / "config")
        self.static_dir = resolve(self.static_dir or Path(__file__).parent / "static")
        if self.cookies_file is not None:
            self.cookies_file = resolve(self.cookies_file)
        if not self.app_token:
            self.app_token = None
        return self

    def ensure_dirs(self) -> None:
        for path in (
            self.download_dir,
            self.library_dir,
            self.config_dir,
            self.config_dir / "plugins",
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        return self.config_dir / "ytdlweb.db"

    @property
    def archive_path(self) -> Path:
        return self.config_dir / "archive.txt"

    @property
    def plugin_dir(self) -> Path:
        return self.config_dir / "plugins"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings().normalize()
