"""Redis connection pool.

One pool per process, shared by the cache, rate limiter, session store, lock
manager, and pub/sub fan-out. Keys are namespaced by ``key_prefix`` so several
environments can share a Redis instance during development without collisions.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from chartnexus.bootstrap.settings import RedisSettings
from redis.asyncio import ConnectionPool, Redis


@dataclass(slots=True)
class RedisClient:
    client: Redis
    pool: ConnectionPool
    key_prefix: str

    @classmethod
    def create(cls, settings: RedisSettings) -> RedisClient:
        pool = ConnectionPool.from_url(
            str(settings.url),
            max_connections=settings.max_connections,
            socket_timeout=settings.socket_timeout_seconds,
            socket_connect_timeout=settings.socket_timeout_seconds,
            health_check_interval=30,
            decode_responses=False,
        )
        return cls(client=Redis(connection_pool=pool), pool=pool, key_prefix=settings.key_prefix)

    def key(self, *parts: str) -> str:
        """Build a namespaced key: ``key("session", sid)`` -> ``cn:session:<sid>``."""
        return ":".join((self.key_prefix, *parts))

    async def close(self) -> None:
        await self.client.aclose()
        await self.pool.disconnect()


def redis_check(redis: RedisClient) -> Callable[[], Awaitable[None]]:
    async def check() -> None:
        await redis.client.ping()

    return check
