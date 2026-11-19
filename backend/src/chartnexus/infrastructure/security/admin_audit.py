"""The admin audit trail: who granted or revoked admin, and when.

A capped Redis list (newest first) plus a structured log line for each entry,
so the record survives in the log pipeline even if Redis is flushed. Entries
hold an account's id and email and the operator's label, nothing secret.
"""

from __future__ import annotations

import json
from typing import Any

from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

AUDIT_LIMIT = 1000


def audit_key(redis: RedisClient) -> str:
    return redis.key("admin", "audit")


class RedisAdminAuditTrail:
    def __init__(self, redis: RedisClient) -> None:
        self._redis = redis

    async def append(self, entry: dict[str, str]) -> None:
        log.warning("admin_audit", **entry)  # warning: role changes must stand out in logs
        key = audit_key(self._redis)
        pipeline = self._redis.client.pipeline(transaction=False)
        pipeline.lpush(key, json.dumps(entry, separators=(",", ":")))
        pipeline.ltrim(key, 0, AUDIT_LIMIT - 1)
        await pipeline.execute()

    async def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        raw: list[bytes] = await self._redis.client.lrange(  # type: ignore[misc]
            audit_key(self._redis), 0, max(0, limit - 1)
        )
        entries: list[dict[str, Any]] = []
        for item in raw:
            try:
                value = json.loads(item)
            except ValueError:
                continue
            if isinstance(value, dict):
                entries.append(value)
        return entries
