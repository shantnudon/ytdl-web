"""Detect a JavaScript runtime for yt-dlp's YouTube extractor.

Since 2025 yt-dlp needs a JS runtime (deno by default) to solve YouTube's
player challenges. Without one, extraction degrades or fails outright, so the
app configures every runtime it can find.

Override with ``JS_RUNTIME=node=/usr/local/bin/node`` (or just ``JS_RUNTIME=deno``).
"""

from __future__ import annotations

import os
import shutil

SUPPORTED = ("deno", "node", "bun")


def detect() -> dict[str, dict[str, str]]:
    """Return a yt-dlp ``js_runtimes`` mapping for runtimes available locally."""
    configured: dict[str, dict[str, str]] = {}

    explicit = (os.environ.get("JS_RUNTIME") or "").strip()
    if explicit:
        name, _, path = explicit.partition("=")
        name = name.strip().lower()
        if name in SUPPORTED:
            configured[name] = {"path": path.strip()} if path.strip() else {}
            return configured

    for name in SUPPORTED:
        binary = shutil.which(name)
        if binary:
            configured[name] = {"path": binary}
    return configured


def available() -> list[str]:
    return sorted(detect())


def describe() -> dict[str, object]:
    runtimes = detect()
    return {
        "runtimes": sorted(runtimes),
        "paths": {name: config.get("path", "") for name, config in runtimes.items()},
        "override": bool((os.environ.get("JS_RUNTIME") or "").strip()),
    }
