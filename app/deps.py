from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from .config import Settings
from .core.worker import DownloadManager
from .db import Database
from .events import Broker


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_broker(request: Request) -> Broker:
    return request.app.state.broker


def get_manager(request: Request) -> DownloadManager:
    return request.app.state.manager


def require_write(request: Request) -> None:
    if not request.app.state.settings.allow_write:
        raise HTTPException(
            status_code=403,
            detail="library writes are disabled: start with ALLOW_WRITE=true to enable them",
        )


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
Db = Annotated[Database, Depends(get_db)]
BrokerDep = Annotated[Broker, Depends(get_broker)]
Manager = Annotated[DownloadManager, Depends(get_manager)]
WriteGuard = Depends(require_write)
