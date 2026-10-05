"""Redis-backed login throttling.

Counts failures, not attempts: a user typing their password correctly a hundred
times is not an attack, and counting successes would let one account lock
another out. After ``max_attempts`` failures the key is locked for a fixed
period.
"""

from __future__ import annotations

from dataclasses import dataclass

from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.shared_kernel.domain.errors import RateLimitError


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    max_attempts: int
    window_seconds: int
    lockout_seconds: int


class RedisLoginRateLimiter:
    """Implements the ``LoginRateLimiter`` port."""

    def __init__(self, redis: RedisClient, policy: RateLimitPolicy) -> None:
        self._redis = redis
        self._policy = policy

    async def check(self, key: str) -> None:
        namespaced = self._key(key)
        lock_ttl = await self._redis.client.ttl(self._lock_key(key))
        if lock_ttl and lock_ttl > 0:
            raise RateLimitError(
                "Too many failed sign-in attempts. Try again shortly.",
                retry_after_seconds=float(lock_ttl),
            )

        raw = await self._redis.client.get(namespaced)
        attempts = int(raw) if raw else 0
        if attempts >= self._policy.max_attempts:
            await self._lock(key)
            raise RateLimitError(
                "Too many failed sign-in attempts. Try again shortly.",
                retry_after_seconds=float(self._policy.lockout_seconds),
            )

    async def record_failure(self, key: str) -> None:
        namespaced = self._key(key)
        pipeline = self._redis.client.pipeline()
        pipeline.incr(namespaced)
        # Only the first failure sets the TTL, so the window is a fixed period
        # after the first failure rather than sliding forward with each one.
        pipeline.expire(namespaced, self._policy.window_seconds, nx=True)
        attempts, _ = await pipeline.execute()

        if int(attempts) >= self._policy.max_attempts:
            await self._lock(key)

    async def reset(self, key: str) -> None:
        await self._redis.client.delete(self._key(key), self._lock_key(key))

    async def _lock(self, key: str) -> None:
        await self._redis.client.set(self._lock_key(key), b"1", ex=self._policy.lockout_seconds)

    def _key(self, key: str) -> str:
        return self._redis.key("ratelimit", key)

    def _lock_key(self, key: str) -> str:
        return self._redis.key("ratelimit", "lock", key)
