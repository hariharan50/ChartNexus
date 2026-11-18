"""Hot-set batching and lock coalescing — how Kite's 1 quote/s stretches."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from chartnexus.contexts.broker_connections.domain.errors import BrokerUnavailableError
from chartnexus.infrastructure.brokers.kite import quote_cache
from chartnexus.infrastructure.brokers.kite.quote_cache import KiteQuoteCache

pytestmark = pytest.mark.unit


class FakeAsyncRedis:
    """Just the commands the cache uses. No expiry: tests clear by hand."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}

    async def mget(self, keys: list[str]) -> list[str | None]:
        return [self.values.get(key) for key in keys]

    async def set(self, key: str, value: str, *, nx: bool = False, px: int | None = None) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def zrevrange(self, key: str, start: int, stop: int) -> list[str]:
        members = sorted(self.zsets.get(key, {}).items(), key=lambda item: -item[1])
        return [member for member, _ in members][start : stop + 1]

    async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeAsyncRedis) -> None:
        self._redis = redis
        self._ops: list[Any] = []

    def set(self, key: str, value: str, px: int | None = None) -> None:
        self._ops.append(lambda: self._redis.values.__setitem__(key, value))

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self._ops.append(lambda: self._redis.zsets.setdefault(key, {}).update(mapping))

    def zremrangebyscore(self, key: str, low: float, high: float) -> None:
        def run() -> None:
            zset = self._redis.zsets.get(key, {})
            for member in [m for m, score in zset.items() if low <= score <= high]:
                del zset[member]

        self._ops.append(run)

    def expire(self, key: str, seconds: int) -> None:
        self._ops.append(lambda: None)

    async def execute(self) -> None:
        for op in self._ops:
            op()


class FakeRedisClient:
    def __init__(self) -> None:
        self.client = FakeAsyncRedis()

    def key(self, *parts: str) -> str:
        return ":".join(("cn", *parts))

    def drop_quotes(self) -> None:
        for key in [k for k in self.client.values if ":quote:" in k]:
            del self.client.values[key]


class RecordingFetch:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def __call__(self, batch: list[str]) -> dict[str, Any]:
        self.calls.append(list(batch))
        return {key: {"last_price": float(len(key))} for key in batch if not key.endswith("BAD")}


def _cache(redis: FakeRedisClient) -> KiteQuoteCache:
    return KiteQuoteCache(redis, api_key="abc123")  # type: ignore[arg-type]


async def test_a_miss_fetches_once_and_a_repeat_is_served_from_cache() -> None:
    redis = FakeRedisClient()
    fetch = RecordingFetch()
    cache = _cache(redis)

    first = await cache.quotes(["NSE:INFY", "NSE:TCS"], fetch)
    second = await cache.quotes(["NSE:INFY"], fetch)

    assert set(first) == {"NSE:INFY", "NSE:TCS"}
    assert second == {"NSE:INFY": first["NSE:INFY"]}
    assert len(fetch.calls) == 1


async def test_recently_asked_instruments_ride_along() -> None:
    """The point of the hot set: one request answers everything being watched."""
    redis = FakeRedisClient()
    fetch = RecordingFetch()
    cache = _cache(redis)

    await cache.quotes(["NSE:NIFTY 50"], fetch)
    redis.drop_quotes()  # the 1.5 s TTL has passed
    await cache.quotes(["NFO:NIFTY26AUGFUT"], fetch)

    assert set(fetch.calls[-1]) == {"NFO:NIFTY26AUGFUT", "NSE:NIFTY 50"}
    # ...so the next spot read costs nothing.
    await cache.quotes(["NSE:NIFTY 50"], fetch)
    assert len(fetch.calls) == 2


async def test_unknown_instruments_are_absent_not_errors() -> None:
    redis = FakeRedisClient()
    result = await _cache(redis).quotes(["NSE:INFY", "NSE:BAD"], RecordingFetch())
    assert set(result) == {"NSE:INFY"}


async def test_large_requests_are_split_at_the_batch_limit() -> None:
    redis = FakeRedisClient()
    fetch = RecordingFetch()
    keys = [f"NFO:X{i}" for i in range(620)]

    result = await _cache(redis).quotes(keys, fetch)

    assert len(result) == 620
    assert [len(call) for call in fetch.calls] == [500, 120]


async def test_a_caller_that_loses_the_lock_reads_the_winners_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(quote_cache, "_POLL_SECONDS", 0.01)
    redis = FakeRedisClient()
    fetch = RecordingFetch()
    cache = _cache(redis)
    lock = redis.key("kite", "quote-lock", "abc123")
    redis.client.values[lock] = "someone-else"

    async def winner_finishes() -> None:
        await asyncio.sleep(0.05)
        redis.client.values[redis.key("kite", "quote", "abc123", "NSE:INFY")] = (
            '{"last_price": 1500.0}'
        )
        del redis.client.values[lock]

    background = asyncio.create_task(winner_finishes())
    result = await cache.quotes(["NSE:INFY"], fetch)
    await background

    assert result == {"NSE:INFY": {"last_price": 1500.0}}
    assert fetch.calls == []  # coalesced: no second request


async def test_a_stuck_lock_degrades_instead_of_queueing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(quote_cache, "_POLL_SECONDS", 0.01)
    monkeypatch.setattr(quote_cache, "_WAIT_SECONDS", 0.05)
    redis = FakeRedisClient()
    redis.client.values[redis.key("kite", "quote-lock", "abc123")] = "stuck"

    with pytest.raises(BrokerUnavailableError):
        await _cache(redis).quotes(["NSE:INFY"], RecordingFetch())


async def test_the_lock_is_released_after_a_failed_fetch() -> None:
    redis = FakeRedisClient()

    async def failing(batch: list[str]) -> dict[str, Any]:
        raise BrokerUnavailableError("kite")

    with pytest.raises(BrokerUnavailableError):
        await _cache(redis).quotes(["NSE:INFY"], failing)

    assert redis.key("kite", "quote-lock", "abc123") not in redis.client.values
