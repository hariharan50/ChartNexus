"""The open-interest sweep runs during the session, and once after it.

Open interest stops moving when the market shuts. On FYERS each contract is its
own request, so the old round-the-clock loop spent ~54,000 calls a day — most of
its budget — re-reading figures that could not change. These tests pin the gate:

* in session: sweep every time, normal cache TTL;
* after the close: one sweep, readings kept until the next open, then nothing;
* that one sweep is claimed in Redis, so two processes cannot both run it;
* a closing pass that never reached a broker gives the claim back;
* an operator's ``--once`` always sweeps.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from chartnexus.entrypoints import futures_oi_runtime
from chartnexus.entrypoints.futures_oi_runtime import _sweep, sweep_once

pytestmark = pytest.mark.unit

IST = ZoneInfo("Asia/Kolkata")
TTL = 45 * 60

IN_SESSION = datetime(2026, 11, 18, 10, 0, tzinfo=IST)  # Wednesday
AFTER_CLOSE = datetime(2026, 11, 18, 16, 0, tzinfo=IST)
UNTIL_THURSDAY_OPEN = (17 * 60 + 15) * 60  # 16:00 -> 09:15 next day
FRIDAY_EVENING = datetime(2026, 11, 20, 16, 0, tzinfo=IST)
UNTIL_MONDAY_OPEN = ((2 * 24 + 17) * 60 + 15) * 60


class FakeRedisClient:
    """The slice of redis.asyncio the gate uses, with real ``nx`` semantics."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expiry: dict[str, int | None] = {}

    async def set(self, name: str, value: str, *, ex: int | None = None, nx: bool = False) -> Any:
        if nx and name in self.values:
            return None
        self.values[name] = value
        self.expiry[name] = ex
        return True

    async def delete(self, name: str) -> int:
        existed = name in self.values
        self.values.pop(name, None)
        self.expiry.pop(name, None)
        return int(existed)


class FakeRedis:
    def __init__(self) -> None:
        self.client = FakeRedisClient()

    def key(self, *parts: str) -> str:
        return ":".join(("cn", *parts))


MARKER = "cn:futures-oi:closed-sweep"


def _settings() -> Any:
    return SimpleNamespace(
        market=SimpleNamespace(
            timezone="Asia/Kolkata", session_open="09:15", session_close="15:40"
        ),
        futures_oi=SimpleNamespace(ttl_seconds=TTL),
    )


class Sweeps:
    """Stands in for the broker walk; records the cache TTL each pass asked for."""

    def __init__(self, result: int | None = 222) -> None:
        self.result = result
        self.ttls: list[int] = []

    async def __call__(self, container: Any, settings: Any, *, ttl_seconds: int) -> int | None:
        self.ttls.append(ttl_seconds)
        return self.result


@pytest.fixture
def sweeps(monkeypatch: pytest.MonkeyPatch) -> Sweeps:
    fake = Sweeps()
    monkeypatch.setattr(futures_oi_runtime, "_sweep_universe", fake)
    return fake


@pytest.fixture
def container() -> Any:
    return SimpleNamespace(redis=FakeRedis())


async def test_in_session_every_pass_sweeps_with_the_normal_ttl(
    sweeps: Sweeps, container: Any
) -> None:
    for _ in range(3):
        assert await _sweep(container, _settings(), IN_SESSION) == 222

    assert sweeps.ttls == [TTL, TTL, TTL]
    assert MARKER not in container.redis.client.values


async def test_in_session_a_leftover_claim_does_not_stop_the_sweep(
    sweeps: Sweeps, container: Any
) -> None:
    container.redis.client.values[MARKER] = "1"

    await _sweep(container, _settings(), IN_SESSION)

    assert sweeps.ttls == [TTL]


async def test_after_the_close_it_sweeps_once_and_keeps_the_readings_to_the_open(
    sweeps: Sweeps, container: Any
) -> None:
    first = await _sweep(container, _settings(), AFTER_CLOSE)

    assert first == 222
    # Readings outlive the night by one normal TTL, so the first in-session
    # sweep replaces them rather than following a blank gap.
    assert sweeps.ttls == [UNTIL_THURSDAY_OPEN + TTL]
    # The claim lapses exactly at the bell, so the next close sweeps again.
    assert container.redis.client.expiry[MARKER] == UNTIL_THURSDAY_OPEN


async def test_after_the_closing_sweep_nothing_more_is_asked_of_the_broker(
    sweeps: Sweeps, container: Any
) -> None:
    await _sweep(container, _settings(), AFTER_CLOSE)
    for hour in (17, 20, 23):
        later = AFTER_CLOSE.replace(hour=hour)
        assert await _sweep(container, _settings(), later) == 0

    assert len(sweeps.ttls) == 1


async def test_a_friday_closing_sweep_holds_through_the_weekend(
    sweeps: Sweeps, container: Any
) -> None:
    await _sweep(container, _settings(), FRIDAY_EVENING)

    assert sweeps.ttls == [UNTIL_MONDAY_OPEN + TTL]
    assert container.redis.client.expiry[MARKER] == UNTIL_MONDAY_OPEN


async def test_two_processes_sharing_redis_sweep_once_between_them(sweeps: Sweeps) -> None:
    # The API's local in-process loop beside a standalone worker.
    shared = FakeRedis()
    api, worker = SimpleNamespace(redis=shared), SimpleNamespace(redis=shared)

    await _sweep(api, _settings(), AFTER_CLOSE)
    await _sweep(worker, _settings(), AFTER_CLOSE)

    assert len(sweeps.ttls) == 1


async def test_a_closing_pass_with_no_broker_gives_the_claim_back(
    monkeypatch: pytest.MonkeyPatch, container: Any
) -> None:
    # No broker was connected at the close. Someone connects Kite at 20:00:
    # the board should get its closing figures then, not tomorrow morning.
    nothing = Sweeps(result=None)
    monkeypatch.setattr(futures_oi_runtime, "_sweep_universe", nothing)
    assert await _sweep(container, _settings(), AFTER_CLOSE) is None
    assert MARKER not in container.redis.client.values

    connected = Sweeps(result=222)
    monkeypatch.setattr(futures_oi_runtime, "_sweep_universe", connected)
    assert await _sweep(container, _settings(), AFTER_CLOSE.replace(hour=20)) == 222
    assert MARKER in container.redis.client.values


async def test_a_closing_sweep_that_dies_is_not_retried_all_night(
    monkeypatch: pytest.MonkeyPatch, container: Any
) -> None:
    calls = {"n": 0}

    async def explodes(*_: Any, **__: Any) -> int:
        calls["n"] += 1
        raise RuntimeError("redis went away mid-write")

    monkeypatch.setattr(futures_oi_runtime, "_sweep_universe", explodes)
    for hour in (16, 17, 18):
        # sweep_once is what the loop calls: it must swallow the failure.
        assert await sweep_once(container, _settings(), now=AFTER_CLOSE.replace(hour=hour)) == 0

    assert calls["n"] == 1


async def test_an_operators_once_sweeps_even_after_the_closing_sweep(
    sweeps: Sweeps, container: Any
) -> None:
    await _sweep(container, _settings(), AFTER_CLOSE)
    before = dict(container.redis.client.values)

    priced = await sweep_once(container, _settings(), now=AFTER_CLOSE.replace(hour=21), force=True)

    assert priced == 222
    assert len(sweeps.ttls) == 2
    assert container.redis.client.values == before  # the claim is left alone
