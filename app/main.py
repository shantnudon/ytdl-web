from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .api import auth as auth_api
from .api import events as events_api
from .api import jobs as jobs_api
from .api import library as library_api
from .api import prefs as prefs_api
from .api import system as system_api
from .config import Settings, get_settings
from .core.worker import DownloadManager, repair_outpaths
from .db import Database
from .events import Broker
from .security import request_token, token_matches

log = logging.getLogger(__name__)

PUBLIC_API = {"/api/health", "/api/auth/login", "/api/auth/status", "/api/auth/logout"}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: https:; media-src 'self'; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'"
    ),
}


class SPAStaticFiles(StaticFiles):
    """Serve the built SPA and fall back to index.html for client routes."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            if "." in path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response("index.html", scope)


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = (settings or get_settings()).normalize()
    cfg.ensure_dirs()

    db = Database(cfg.db_path)
    broker = Broker()
    manager = DownloadManager(db, broker, cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        broker.bind_loop(asyncio.get_running_loop())
        interrupted = db.mark_interrupted()
        if interrupted:
            log.warning("marked %s running job(s) as interrupted", interrupted)
        repaired = repair_outpaths(db, cfg.download_dir)
        if repaired:
            log.info("repaired %s job output path(s)", repaired)
        await manager.start()
        try:
            yield
        finally:
            await manager.stop()
            db.close()

    app = FastAPI(
        title="ytdlweb",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = cfg
    app.state.db = db
    app.state.broker = broker
    app.state.manager = manager

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    @app.middleware("http")
    async def auth_guard(request: Request, call_next):
        token = cfg.app_token
        if token:
            path = request.url.path
            if path.startswith("/api/") and path not in PUBLIC_API:
                if not token_matches(request_token(request), token):
                    return JSONResponse({"detail": "authentication required"}, status_code=401)
                needs_csrf = request.method not in ("GET", "HEAD", "OPTIONS")
                if needs_csrf and request.headers.get("x-requested-with") != "ytdlweb":
                    return JSONResponse(
                        {"detail": "missing X-Requested-With header"}, status_code=403
                    )
        return await call_next(request)

    app.include_router(system_api.router)
    app.include_router(auth_api.router)
    app.include_router(jobs_api.router)
    app.include_router(jobs_api.probe_router)
    app.include_router(library_api.router)
    app.include_router(prefs_api.router)
    app.include_router(events_api.router)

    static_dir = Path(cfg.static_dir)
    index_html = static_dir / "index.html"

    if index_html.is_file():
        app.mount("/", SPAStaticFiles(directory=str(static_dir), html=True), name="spa")
    else:

        @app.get("/")
        def missing_ui() -> JSONResponse:
            return JSONResponse(
                {
                    "detail": "UI is not built",
                    "fix": "cd frontend && npm install && npm run build",
                    "api_docs": "/api/docs",
                }
            )

    return app


app = create_app()
