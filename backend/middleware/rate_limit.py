"""In-memory rate limiter middleware. No external dependencies.

Uses sliding window counters per IP + path prefix.
"""

import time
from collections import defaultdict
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitEntry:
    __slots__ = ("timestamps",)

    def __init__(self):
        self.timestamps: list[float] = []


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding window rate limiter.

    Rules format: list of (path_prefix, max_requests, window_seconds).
    Requests not matching any rule are not rate-limited.
    """

    def __init__(self, app, rules: Optional[list[tuple[str, int, int]]] = None):
        super().__init__(app)
        self.rules = rules or []
        self._buckets: dict[str, RateLimitEntry] = defaultdict(RateLimitEntry)
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # cleanup stale entries every 5 min

    def _get_client_ip(self, request: Request) -> str:
        # Support reverse proxy (nginx)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _match_rule(self, path: str, method: str) -> Optional[tuple[int, int]]:
        for prefix, max_req, window in self.rules:
            if path.startswith(prefix):
                return max_req, window
        return None

    def _cleanup_stale(self, now: float):
        """Remove entries older than max window to prevent memory leak."""
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        max_window = max((w for _, _, w in self.rules), default=60)
        cutoff = now - max_window * 2
        stale_keys = [k for k, v in self._buckets.items() if not v.timestamps or v.timestamps[-1] < cutoff]
        for k in stale_keys:
            del self._buckets[k]

    async def dispatch(self, request: Request, call_next) -> Response:
        now = time.time()
        self._cleanup_stale(now)

        path = request.url.path
        rule = self._match_rule(path, request.method)
        if not rule:
            return await call_next(request)

        max_req, window = rule
        client_ip = self._get_client_ip(request)
        key = f"{client_ip}:{path.split('/')[2] if len(path.split('/')) > 2 else path}"

        entry = self._buckets[key]
        # Remove timestamps outside window
        cutoff = now - window
        entry.timestamps = [t for t in entry.timestamps if t > cutoff]

        if len(entry.timestamps) >= max_req:
            retry_after = int(entry.timestamps[0] + window - now) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Slow down."},
                headers={"Retry-After": str(retry_after)},
            )

        entry.timestamps.append(now)
        return await call_next(request)
