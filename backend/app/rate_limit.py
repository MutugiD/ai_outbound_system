"""Simple rate limiting dependency (Redis-backed, in-memory fallback).

This is intentionally lightweight: it protects high-risk endpoints (auth,
scraping, enrichment) from brute force and cost-amplification attacks.

For production, Redis is strongly recommended to make limits consistent across
multiple API replicas.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from app.config import settings

_memory_counters: dict[str, tuple[int, int]] = {}  # {key: (window_id, count)}


def _get_client_ip(request: Request) -> str:
    # Prefer the direct socket address. (If running behind a proxy/load balancer,
    # configure the platform to preserve client IP safely.)
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@dataclass(frozen=True)
class RateLimit:
    limit: int
    window_seconds: int
    scope: str


class RateLimiter:
    def __init__(self) -> None:
        self._redis = None

    async def _get_redis(self):
        if self._redis is not None:
            return self._redis
        try:
            from redis.asyncio import Redis

            self._redis = Redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
            return self._redis
        except Exception:
            self._redis = None
            return None

    async def check(self, request: Request, rule: RateLimit) -> None:
        ip = _get_client_ip(request)
        window_id = int(time.time() // rule.window_seconds)
        key = f"rl:{rule.scope}:{ip}:{window_id}"

        redis = await self._get_redis()
        if redis is not None:
            try:
                count = await redis.incr(key)
                if count == 1:
                    # expire slightly after window ends
                    await redis.expire(key, rule.window_seconds + 5)
                if count > rule.limit:
                    raise HTTPException(status_code=429, detail="Rate limit exceeded")
                return
            except HTTPException:
                raise
            except Exception:
                # Fall back to in-memory counters if Redis is unavailable
                pass

        prev = _memory_counters.get(key)
        if prev is None or prev[0] != window_id:
            _memory_counters[key] = (window_id, 1)
            return

        count = prev[1] + 1
        _memory_counters[key] = (window_id, count)
        if count > rule.limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")


_limiter = RateLimiter()


def rate_limit(limit: int, window_seconds: int, scope: str):
    """FastAPI dependency factory: `Depends(rate_limit(...))`."""

    rule = RateLimit(limit=limit, window_seconds=window_seconds, scope=scope)

    async def _dep(request: Request) -> None:
        await _limiter.check(request, rule)

    return _dep

