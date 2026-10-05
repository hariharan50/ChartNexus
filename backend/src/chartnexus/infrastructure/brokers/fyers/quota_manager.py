"""Broker request quota.

FYERS enforces per-second and per-day limits per application. Exceeding them
gets the application throttled, so the limit is enforced on our side first —
where we can degrade to cached data — instead of discovering it as a rejection.

Counters live in Redis and are keyed by app id, so all workers share one budget.
A tenant's own application has its own budget, which is the point of per-tenant
credentials.
"""

from __future__ import annotations

from dataclasses import dataclass

from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.shared_kernel.domain.errors import RateLimitError

_SECOND_WINDOW = 1
_DAY_WINDOW = 86_400


@dataclass(frozen=True, slots=True)
class QuotaPolicy:
    requests_per_second: int = 8
    requests_per_day: int = 100_000


class RedisQuotaManager:
    """Fixed-window counters. Approximate at window edges, which is fine here:
    the goal is staying under a broker limit, not exact accounting."""

    def __init__(self, redis: RedisClient, policy: QuotaPolicy) -> None:
        self._redis = redis
        self._policy = policy

    async def acquire(self, app_id: str) -> None:
        """Consume one request from the budget, or raise.

        Raising ``RateLimitError`` rather than sleeping is deliberate: the
        caller can serve cached data immediately, which is a better answer than
        a request that blocks for a second.
        """
        await self._check(
            key=self._redis.key("broker", "quota", app_id, "s"),
            limit=self._policy.requests_per_second,
            window=_SECOND_WINDOW,
            message="Broker request rate exceeded. Showing recent data.",
        )
        await self._check(
            key=self._redis.key("broker", "quota", app_id, "d"),
            limit=self._policy.requests_per_day,
            window=_DAY_WINDOW,
            message="Daily broker request limit reached.",
        )

    async def _check(self, *, key: str, limit: int, window: int, message: str) -> None:
        pipeline = self._redis.client.pipeline()
        pipeline.incr(key)
        # Only the first increment sets the expiry, so the window is fixed from
        # the first request rather than sliding forward with each one.
        pipeline.expire(key, window, nx=True)
        used, _ = await pipeline.execute()

        if int(used) > limit:
            ttl = await self._redis.client.ttl(key)
            raise RateLimitError(message, retry_after_seconds=float(max(ttl, 1)))


class NullQuotaManager:
    """No-op, for tests and the mock provider."""

    async def acquire(self, app_id: str) -> None:  # noqa: ARG002 — matches the interface
        return
