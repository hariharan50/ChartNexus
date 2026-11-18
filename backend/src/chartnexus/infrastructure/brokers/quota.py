"""Per-second request buckets for brokers that publish per-endpoint limits.

Kite limits each API key separately per endpoint class — ``/quote`` at one
request a second, historical at three, everything else at ten. One shared
counter (what the FYERS quota uses) would either starve quotes behind
history or let a burst of quotes through at ten a second and collect 429s.

Counters live in Redis keyed by ``(broker, app key, bucket, epoch second)``,
so every worker process shares one budget per API key.

``acquire(..., max_wait=…)`` may wait for the *next* second instead of
refusing. That is the right trade for a user-facing quote — data a moment
later beats a blank tile — and the wrong one for a background sweep, which
passes ``max_wait=0`` and lets the caller degrade.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.shared_kernel.domain.errors import RateLimitError

_DAY_SECONDS = 86_400


@dataclass(frozen=True, slots=True)
class BucketPolicy:
    per_second: dict[str, int] = field(default_factory=dict)
    per_day: int = 200_000


class RedisBucketQuota:
    def __init__(
        self, redis: RedisClient, *, broker: str, app_key: str, policy: BucketPolicy
    ) -> None:
        self._redis = redis
        self._broker = broker
        self._app_key = app_key
        self._policy = policy

    async def acquire(self, bucket: str, *, max_wait: float = 0.0) -> None:
        """Take one request from ``bucket``, waiting up to ``max_wait`` seconds.

        Raises ``RateLimitError`` when the bucket stays full past ``max_wait``,
        or when the daily allowance is spent.
        """
        limit = self._policy.per_second.get(bucket)
        if limit is None:
            msg = f"unknown quota bucket {bucket!r}"
            raise ValueError(msg)

        deadline = time.monotonic() + max_wait
        while True:
            second = int(time.time())
            used = await self._incr(self._key(bucket, str(second)), ttl=2)
            if used <= limit:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RateLimitError(
                    "Broker request rate exceeded. Showing recent data.",
                    retry_after_seconds=1.0,
                )
            # Sleep to the top of the next second, not a fixed tick: windows are
            # aligned to wall-clock seconds, so that is when a slot frees up.
            await asyncio.sleep(min(remaining, max(0.01, (second + 1) - time.time())))

        day_used = await self._incr(self._key("day", time.strftime("%Y%m%d")), ttl=_DAY_SECONDS)
        if day_used > self._policy.per_day:
            raise RateLimitError("Daily broker request limit reached.", retry_after_seconds=3600.0)

    def _key(self, *parts: str) -> str:
        return self._redis.key("broker", "quota", self._broker, self._app_key, *parts)

    async def _incr(self, key: str, *, ttl: int) -> int:
        pipeline = self._redis.client.pipeline()
        pipeline.incr(key)
        pipeline.expire(key, ttl, nx=True)
        used, _ = await pipeline.execute()
        return int(used)


class NullBucketQuota:
    """No-op, for tests."""

    async def acquire(self, bucket: str, *, max_wait: float = 0.0) -> None:  # noqa: ARG002
        return
