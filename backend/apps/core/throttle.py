"""Brute-force / abuse throttling — cache-backed and dependency-free.

Counts attempts per identifier (client IP and/or the submitted email) in the
Django cache; once a threshold is crossed within a window, the identifier is
locked for a cooldown. Deterministic and side-effect free apart from the cache
and a single audit record when a lock trips.

NOTE: the default cache is per-process (LocMemCache). In multi-process /
multi-host production, configure a shared cache (e.g. Redis) via settings.CACHES
so the limits apply across every worker.
"""
from __future__ import annotations

import math
import time

from django.core.cache import cache

from apps.audit.service import record as audit


def client_ip(request) -> str:
    """Best-effort client IP. Honours the first X-Forwarded-For hop (set by a
    trusted proxy); falls back to REMOTE_ADDR."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "unknown"


def _minutes(seconds: int) -> int:
    return max(1, math.ceil(seconds / 60))


def too_many_message(seconds: int) -> str:
    return (
        "Too many attempts. For your security this has been paused — "
        f"please try again in about {_minutes(seconds)} minute(s)."
    )


class RateLimiter:
    def __init__(self, scope: str, *, limit: int, window: int, lock: int | None = None):
        self.scope = scope
        self.limit = limit
        self.window = window
        self.lock = lock or window

    def _count_key(self, ident: str) -> str:
        return f"thr:{self.scope}:c:{ident}"

    def _lock_key(self, ident: str) -> str:
        return f"thr:{self.scope}:l:{ident}"

    def retry_after(self, ident: str) -> int:
        """Seconds until this identifier is allowed again (0 if not locked)."""
        until = cache.get(self._lock_key(ident))
        return max(0, int(until - time.time())) if until else 0

    def hit(self, ident: str) -> int:
        """Record one attempt. Returns the cooldown (seconds) if this attempt
        tripped — or is already under — a lock; 0 while still within budget."""
        locked = self.retry_after(ident)
        if locked:
            return locked
        n = (cache.get(self._count_key(ident)) or 0) + 1
        cache.set(self._count_key(ident), n, self.window)
        if n >= self.limit:
            cache.set(self._lock_key(ident), time.time() + self.lock, self.lock)
            cache.delete(self._count_key(ident))
            audit("security.lockout", target=f"{self.scope}:{ident}",
                  summary=f"locked after {n} attempt(s) for {self.lock}s")
            return self.lock
        return 0

    def reset(self, ident: str) -> None:
        cache.delete(self._count_key(ident))
        cache.delete(self._lock_key(ident))


# --- configured limiters ----------------------------------------------------
# Login locks a single account faster than a whole IP (which many users share).
LOGIN_USER = RateLimiter("login_user", limit=5, window=900, lock=900)     # 5 / 15min
LOGIN_IP = RateLimiter("login_ip", limit=20, window=900, lock=900)        # 20 / 15min
SIGNUP_IP = RateLimiter("signup_ip", limit=10, window=3600, lock=3600)    # 10 / hour
RESET_IP = RateLimiter("reset_ip", limit=8, window=3600, lock=3600)       # 8 / hour
RESET_USER = RateLimiter("reset_user", limit=5, window=3600, lock=3600)   # 5 / hour


def login_retry_after(email: str, ip: str) -> int:
    return max(LOGIN_USER.retry_after(email), LOGIN_IP.retry_after(ip))


def login_record_failure(email: str, ip: str) -> None:
    LOGIN_USER.hit(email)
    LOGIN_IP.hit(ip)


def login_reset(email: str, ip: str) -> None:
    LOGIN_USER.reset(email)
    LOGIN_IP.reset(ip)


def reset_retry_after(email: str, ip: str) -> int:
    return max(RESET_IP.retry_after(ip), RESET_USER.retry_after(email) if email else 0)


def reset_record(email: str, ip: str) -> None:
    RESET_IP.hit(ip)
    if email:
        RESET_USER.hit(email)
