from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

PYPI_YTDLP = "https://pypi.org/pypi/yt-dlp/json"


def _settings():
    from .config import get_settings

    return get_settings()


def update_extractors(plugin_dir: Path) -> dict:
    """Install the newest pure-python yt-dlp wheel into the plugin directory.

    This is how a frozen single-file build gets extractor fixes without a new
    release: ``app._ytdlp`` prepends the plugin dir to ``sys.path``.
    """
    with urllib.request.urlopen(PYPI_YTDLP, timeout=30) as response:
        meta = json.load(response)

    version = meta["info"]["version"]
    wheel = next(
        (
            item
            for item in meta.get("urls", [])
            if item.get("packagetype") == "bdist_wheel"
            and item["filename"].endswith("py3-none-any.whl")
        ),
        None,
    )
    if wheel is None:
        raise RuntimeError("no pure-python wheel published for yt-dlp")

    with urllib.request.urlopen(wheel["url"], timeout=120) as response:
        payload = response.read()

    plugin_dir.mkdir(parents=True, exist_ok=True)
    staging = plugin_dir / ".staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for name in archive.namelist():
                if name.startswith(("/", "..")) or ".." in Path(name).parts:
                    raise RuntimeError(f"unsafe path in wheel: {name}")
            archive.extractall(staging)
        new_pkg = staging / "yt_dlp"
        if not new_pkg.is_dir():
            raise RuntimeError("unexpected wheel layout (yt_dlp/ missing)")
        target = plugin_dir / "yt_dlp"
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(new_pkg), str(target))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return {
        "updated": True,
        "version": version,
        "path": str(plugin_dir / "yt_dlp"),
        "restart_required": True,
    }


def doctor() -> dict:
    from . import __version__
    from . import _ytdlp as ytdlp
    from .core.ffmpeg import resolve_ffmpeg
    from .core.jsruntime import describe as describe_js

    cfg = _settings()
    cfg.ensure_dirs()
    return {
        "version": __version__,
        "python": sys.version.split()[0],
        "yt_dlp": ytdlp.version(),
        "js_runtime": describe_js(),
        "plugin_override": (cfg.plugin_dir / "yt_dlp").is_dir(),
        "plugin_dir": str(cfg.plugin_dir),
        "ffmpeg": resolve_ffmpeg(),
        "dirs": {
            "data": str(cfg.data_dir),
            "downloads": str(cfg.download_dir),
            "library": str(cfg.library_dir),
            "config": str(cfg.config_dir),
        },
        "writable": {
            "downloads": _writable(cfg.download_dir),
            "library": _writable(cfg.library_dir),
            "config": _writable(cfg.config_dir),
        },
        "allow_write": cfg.allow_write,
        "auth_required": bool(cfg.app_token),
    }


def _writable(path: Path) -> bool:
    probe = path / ".ytdlweb-write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    cfg = _settings()
    cfg.ensure_dirs()
    host = args.host or cfg.app_host
    port = args.port or cfg.app_port
    print(f"ytdlweb {_version()} -> http://{host}:{port}")
    print(f"  downloads: {cfg.download_dir}")
    print(f"  library  : {cfg.library_dir}")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level=cfg.log_level,
        reload=bool(args.reload),
    )
    return 0


def _version() -> str:
    from . import __version__

    return __version__


def _scan() -> int:
    from .db import Database
    from .library.index import scan

    cfg = _settings()
    cfg.ensure_dirs()
    db = Database(cfg.db_path)
    try:
        result = scan(cfg.library_dir, db)
    finally:
        db.close()
    print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv = ["serve", *argv]

    parser = argparse.ArgumentParser(prog="ytdlweb", description="Self-hosted yt-dlp web UI")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the web server")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true", help="auto-reload for development")

    sub.add_parser("doctor", help="print environment diagnostics")
    sub.add_parser("scan", help="index the music library and exit")
    sub.add_parser("update-extractors", help="install the latest yt-dlp extractors")

    args = parser.parse_args(argv)

    if args.command == "serve":
        return _serve(args)
    if args.command == "doctor":
        print(json.dumps(doctor(), indent=2))
        return 0
    if args.command == "scan":
        return _scan()
    if args.command == "update-extractors":
        cfg = _settings()
        print(json.dumps(update_extractors(cfg.plugin_dir), indent=2))
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
