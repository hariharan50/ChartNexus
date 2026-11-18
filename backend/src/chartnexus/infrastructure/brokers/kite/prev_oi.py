"""Previous-session open interest, which Kite does not publish.

Every OI-change number in ChartNexus — the option chain's ``oich`` column,
build-up classification on the futures board — needs yesterday's closing OI.
FYERS returns it; Kite does not. But before the 09:15 open, Kite's ``oi`` field
*is* the previous session's close, because nothing has traded since. So a
capture taken pre-open, keyed by the session it will be compared against, gives
the baseline for the whole day.

Stored in Redis as one hash per session date: ``instrument_token → oi``, kept
for two days. Shared across processes and tenants: OI is a fact about the
market, not about whoever fetched it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Iterable, Mapping
from datetime import date
from typing import Any, cast

from chartnexus.infrastructure.cache.redis.client import RedisClient

_RETAIN_SECONDS = 2 * 86_400


class PreviousOpenInterest:
    def __init__(self, redis: RedisClient) -> None:
        self._redis = redis

    def _key(self, session: date) -> str:
        return self._redis.key("kite", "prev-oi", session.isoformat())

    async def read(self, session: date, tokens: Iterable[int]) -> dict[int, int]:
        wanted = [str(token) for token in tokens]
        if not wanted:
            return {}
        values = await cast(
            "Awaitable[list[Any]]", self._redis.client.hmget(self._key(session), wanted)
        )
        result: dict[int, int] = {}
        for token, value in zip(wanted, values, strict=True):
            if value is None:
                continue
            try:
                result[int(token)] = int(value)
            except ValueError:
                continue
        return result

    async def write(self, session: date, readings: Mapping[int, int]) -> None:
        if not readings:
            return
        key = self._key(session)
        pipeline = self._redis.client.pipeline()
        pipeline.hset(key, mapping={str(token): str(oi) for token, oi in readings.items()})
        pipeline.expire(key, _RETAIN_SECONDS)
        await pipeline.execute()
