from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from starlette.requests import Request


def token_matches(candidate: str | None, expected: str | None) -> bool:
    if not candidate or not expected:
        return False
    import hmac

    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def request_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header and header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get("ytdlweb_token")


class RateLimiter:
    """Tiny in-process sliding window; enough for a single-user service."""

    def __init__(self, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._events[key]
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
