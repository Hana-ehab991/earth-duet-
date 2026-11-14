"""Small in-memory sliding-window rate limiter.

LIMITATION: state lives in this process only. With several uvicorn/gunicorn workers (or several instances) each
worker counts separately, so the effective limit is roughly N x the configured limit. Behind a load balancer the
client address is the proxy's unless EARTH_DUET_TRUST_FORWARDED_FOR is enabled for a trusted proxy. Treat this as
protection against accidental floods from one client, not as a security boundary. Use a gateway / API-management
layer for real abuse protection.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Optional


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic, max_keys: int = 10_000):
        self.limit, self.window_s, self._clock, self._max_keys = int(limit), float(window_s), clock, max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.limit > 0

    def check(self, key: str) -> Optional[float]:
        """Record a request. Returns None if allowed, else the seconds to wait before retrying."""
        if not self.enabled:
            return None
        now = self._clock()
        with self._lock:
            if len(self._hits) >= self._max_keys:           # bound memory: drop idle clients
                for k in [k for k, q in self._hits.items() if not q or q[-1] <= now - self.window_s]:
                    del self._hits[k]
                if len(self._hits) >= self._max_keys and key not in self._hits:
                    return self.window_s                      # still full of active clients: refuse new ones
            q = self._hits.setdefault(key, deque())
            while q and q[0] <= now - self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return max(0.1, q[0] + self.window_s - now)
            q.append(now)
            return None
