"""The open-interest cache, and what it does when Redis is unhappy.

The board is drawn from this on every refresh, so its failure modes matter more
than its happy path: a cache that raises takes the page down, and one that
hands back a stale reading makes the board classify today's price move against
some earlier session's baseline and report it with total confidence.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from marketcompass.infrastructure.futures.oi_cache import (
    CachedOpenInterest,
    RedisOpenInterestCache,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 21, 7, 0, tzinfo=UTC)


class FakeRedisClient:
    """Enough of the hash API for this cache, plus a way to make it fail."""

    def __init__(self, *, fails: bool = False) -> None:
        self.hash: dict[bytes, bytes] = {}
        self.expires: int | None = None
        self._fails = fails

    async def hgetall(self, key: str) -> dict[bytes, bytes]:
        if self._fails:
            raise ConnectionError("redis is down")
        return dict(self.hash)

    async def hset(self, key: str, *, mapping: dict[str, str]) -> int:
        if self._fails:
            raise ConnectionError("redis is down")
        self.hash.update({k.encode(): v.encode() for k, v in mapping.items()})
        return len(mapping)

    async def expire(self, key: str, seconds: int) -> bool:
        self.expires = seconds
        return True


class FakeRedis:
    def __init__(self, *, fails: bool = False) -> None:
        self.client = FakeRedisClient(fails=fails)

    def key(self, *parts: str) -> str:
        return ":".join(("mc", *parts))


def reading(oi: int = 1000, previous: int | None = 900) -> CachedOpenInterest:
    return CachedOpenInterest(open_interest=oi, previous_open_interest=previous, observed_at=NOW)


async def test_a_sweep_round_trips() -> None:
    redis = FakeRedis()
    cache = RedisOpenInterestCache(redis)  # type: ignore[arg-type]

    await cache.write_all({"RELIANCE": reading(), "TCS": reading(2000, 1800)})
    back = await cache.read_all()

    assert set(back) == {"RELIANCE", "TCS"}
    assert back["TCS"].open_interest == 2000
    assert back["TCS"].previous_open_interest == 1800
    assert back["RELIANCE"].observed_at == NOW


async def test_a_reading_without_a_previous_close_survives() -> None:
    """Some contracts have no prior-day figure; that is a missing baseline,
    not a corrupt entry."""
    redis = FakeRedis()
    cache = RedisOpenInterestCache(redis)  # type: ignore[arg-type]

    await cache.write_all({"NEWLIST": reading(previous=None)})

    assert (await cache.read_all())["NEWLIST"].previous_open_interest is None


async def test_entries_are_given_a_lifetime() -> None:
    """Stale open interest that looks current is worse than none: the board
    would measure today's move against an older session's baseline."""
    redis = FakeRedis()

    await RedisOpenInterestCache(redis, ttl_seconds=600).write_all({"X": reading()})  # type: ignore[arg-type]

    assert redis.client.expires == 600


async def test_a_redis_outage_degrades_a_column_not_the_page() -> None:
    cache = RedisOpenInterestCache(FakeRedis(fails=True))  # type: ignore[arg-type]

    assert await cache.read_all() == {}
    # And writing must not propagate either — a failed sweep retries next pass.
    await cache.write_all({"RELIANCE": reading()})


async def test_a_corrupt_entry_costs_one_row_not_the_board() -> None:
    redis = FakeRedis()
    cache = RedisOpenInterestCache(redis)  # type: ignore[arg-type]
    await cache.write_all({"GOOD": reading()})
    redis.client.hash[b"BROKEN"] = b"{not json"
    redis.client.hash[b"PARTIAL"] = json.dumps({"oi": 5}).encode()

    back = await cache.read_all()

    assert set(back) == {"GOOD"}


async def test_an_empty_sweep_is_not_written() -> None:
    """A sweep that priced nothing must not blank yesterday's readings."""
    redis = FakeRedis()
    cache = RedisOpenInterestCache(redis)  # type: ignore[arg-type]
    await cache.write_all({"RELIANCE": reading()})

    await cache.write_all({})

    assert set(await cache.read_all()) == {"RELIANCE"}
