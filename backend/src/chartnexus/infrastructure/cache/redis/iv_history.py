"""Intraday ATM-IV history, used to rank today's reading as a percentile.

No cross-day history exists yet — this is deliberately reset every session: a
Redis sorted set keyed by symbol and trading date, expiring well after the
session ends so a quiet weekend never carries Friday's readings into Monday.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from chartnexus.infrastructure.cache.redis.client import RedisClient

_TTL_SECONDS = 26 * 60 * 60  # a session plus slack; never spans into the next day's open


class RedisIvHistoryRecorder:
    """Implements ``market_data``'s ``IvHistoryRecorder`` port."""

    def __init__(self, redis: RedisClient) -> None:
        self._redis = redis

    async def record_and_rank(self, *, symbol: str, session_date: date, atm_iv: Decimal) -> Decimal:
        key = self._redis.key("iv-history", symbol, session_date.isoformat())
        value = float(atm_iv)
        # The member must be unique per reading or ZADD would overwrite an
        # earlier one sharing the same IV value instead of adding a new entry.
        member = f"{value}:{uuid4()}"

        await self._redis.client.zadd(key, {member: value})
        await self._redis.client.expire(key, _TTL_SECONDS)

        below_or_equal = await self._redis.client.zcount(key, "-inf", value)
        total = await self._redis.client.zcard(key)
        if total <= 0:
            return Decimal("0")
        rank = (Decimal(below_or_equal) / Decimal(total)) * Decimal(100)
        return rank.quantize(Decimal("0.1"))
