"""The open-interest cache the futures board reads from.

Open interest is the one number the build-up classification cannot do without,
and the only broker endpoint that carries it accepts **one contract per
request** — verified against the live API, which rejects a list outright with
"More than one symbol is not allowed". Fetching it with the board would mean
two hundred-odd requests every refresh: roughly 340,000 a day against a
100,000 quota, and longer to complete than the refresh interval itself.

So it is swept on a slow cadence and cached here. That is sound rather than
merely expedient: open interest is a daily aggregate that moves in minutes, not
ticks, so a reading a few minutes old is as good as a fresh one — unlike price,
which is fetched with every board.

**Cached globally, not per tenant.** Open interest is a fact about the market,
not about whoever asked. A tenant's broker connection is only the means of
fetching it, so one sweep serves everybody and the cost does not multiply with
the user count.

Entries carry the moment they were observed and expire on their own, because a
stale reading that looks current is worse than no reading: the board would
classify today's price move against a baseline from some earlier session and
report it with complete confidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from marketcompass.infrastructure.cache.redis.client import RedisClient
from marketcompass.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

_KEY = "futures-oi"


def _key_for(series: int) -> str:
    """One hash per contract series.

    The near month keeps the original un-suffixed key so a deploy does not
    start with an empty board while the first sweep runs. Back months get
    their own hash rather than a prefixed field, so a sweep that covers only
    the front month leaves the others genuinely absent — which is what the
    board needs in order to say "not swept" instead of showing a stale figure
    under a contract it was never read for.
    """
    return _KEY if series <= 0 else f"{_KEY}:s{series}"


#: How long a reading stays usable. Generous against the sweep interval so a
#: single failed pass does not blank the board, but far short of a session so
#: yesterday's figures can never masquerade as today's.
DEFAULT_TTL_SECONDS = 45 * 60


@dataclass(frozen=True, slots=True)
class CachedOpenInterest:
    open_interest: int
    previous_open_interest: int | None
    observed_at: datetime

    def age_seconds(self, now: datetime) -> float:
        return max((now - self.observed_at).total_seconds(), 0.0)


class RedisOpenInterestCache:
    """A Redis hash of symbol to open interest, written by the sweeper."""

    def __init__(self, redis: RedisClient, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    def _hash(self) -> Any:
        """The Redis client, untyped.

        redis-py declares its hash commands as ``Awaitable[T] | T`` so one class
        can serve both the sync and async APIs. That union is not awaitable as
        far as the type checker is concerned, and the alternative is a cast at
        every call site.
        """
        return self._redis.client

    async def read_all(self, series: int = 0) -> dict[str, CachedOpenInterest]:
        """Every cached reading for one series, keyed by canonical symbol.

        One round trip for the whole board rather than a lookup per row — the
        caller needs all of it or none of it.
        """
        try:
            raw = await self._hash().hgetall(self._redis.key(_key_for(series)))
        except Exception as exc:
            # The board is still worth drawing without open interest, so a
            # cache outage degrades a column rather than the page.
            log.warning("futures_oi_cache_read_failed", error=repr(exc))
            return {}

        readings: dict[str, CachedOpenInterest] = {}
        for key, value in (raw or {}).items():
            symbol = key.decode() if isinstance(key, bytes) else str(key)
            parsed = _decode(value)
            if parsed is not None:
                readings[symbol] = parsed
        return readings

    async def write_all(self, readings: dict[str, CachedOpenInterest], series: int = 0) -> None:
        """Replace one series' cache with a completed sweep.

        Written as one mapping so the board never observes a half-updated
        board — some contracts from this sweep and some from the last.
        """
        if not readings:
            return
        payload = {
            symbol: json.dumps(
                {
                    "oi": reading.open_interest,
                    "pdoi": reading.previous_open_interest,
                    "at": reading.observed_at.isoformat(),
                }
            )
            for symbol, reading in readings.items()
        }
        try:
            key = self._redis.key(_key_for(series))
            client = self._hash()
            await client.hset(key, mapping=payload)
            await client.expire(key, self._ttl)
        except Exception as exc:
            log.warning("futures_oi_cache_write_failed", error=repr(exc))


def _decode(value: object) -> CachedOpenInterest | None:
    try:
        raw = value.decode() if isinstance(value, bytes) else str(value)
        data = json.loads(raw)
        return CachedOpenInterest(
            open_interest=int(data["oi"]),
            previous_open_interest=(int(data["pdoi"]) if data.get("pdoi") is not None else None),
            observed_at=datetime.fromisoformat(data["at"]).astimezone(UTC),
        )
    except Exception:
        # A malformed entry is one missing row, not a broken board.
        return None
