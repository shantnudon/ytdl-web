"""In-process pub/sub used to stream job progress to the browser over SSE."""

from __future__ import annotations

import asyncio
import itertools
import threading
from collections import deque
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any


class Broker:
    def __init__(self, history: int = 500) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._history: deque[dict[str, Any]] = deque(maxlen=history)
        self._ids = itertools.count(1)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, kind: str, data: dict[str, Any]) -> dict[str, Any]:
        event = {"id": next(self._ids), "type": kind, "data": data}
        with self._lock:
            self._history.append(event)
            subscribers = list(self._subscribers)
        for queue in subscribers:
            # Slow consumer: drop the frame instead of blocking downloads.
            with suppress(asyncio.QueueFull):
                queue.put_nowait(event)
        return event

    def publish_threadsafe(self, kind: str, data: dict[str, Any]) -> None:
        """Callable from worker threads (yt-dlp progress hooks run off-loop)."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self.publish, kind, data)

    async def subscribe(self, since: int | None = None) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        with self._lock:
            self._subscribers.add(queue)
            replay = [e for e in self._history if since is not None and e["id"] > since]
        try:
            for event in replay:
                queue.put_nowait(event)
            while True:
                yield await queue.get()
        finally:
            with self._lock:
                self._subscribers.discard(queue)
