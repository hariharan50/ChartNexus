"""The ingest loop's announcement of a committed snapshot.

The rule that matters is subordination: the archive is the product and the
notification is a courtesy. A Redis failure must cost the prompt, never the
capture loop — a loop that died because Redis hiccuped has lost a session of
history nothing can recover.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from chartnexus.bootstrap.settings import RealtimeSettings, Settings
from chartnexus.contexts.market_ingestion.application.capture import CommittedSnapshot
from chartnexus.entrypoints import ingest_runtime

COMMITTED = CommittedSnapshot(
    symbol="NIFTY",
    session_date=date(2026, 10, 9),
    captured_at=datetime(2026, 10, 9, 8, 30, tzinfo=UTC),
    spot=Decimal("24512.35"),
    source="mock",
    expiry="2026-10-14",
)


class FakePubSub:
    def __init__(self, *, fail: bool = False) -> None:
        self.published: list[tuple[str, Mapping[str, Any]]] = []
        self._fail = fail

    async def publish(self, channel: str, payload: Mapping[str, Any]) -> int:
        if self._fail:
            raise ConnectionError("redis is unreachable")
        self.published.append((channel, payload))
        return 0


@pytest.fixture
def pubsub(monkeypatch: pytest.MonkeyPatch) -> FakePubSub:
    fake = FakePubSub()
    monkeypatch.setattr(ingest_runtime, "RedisPubSub", lambda _redis: fake)
    return fake


@pytest.fixture
def settings() -> Settings:
    return Settings()


def _container() -> Any:
    """A stand-in whose only used attribute is `redis`.

    `publish_committed` reads `container.redis` to build the pub/sub adapter, and
    the adapter itself is patched out, so the value is never touched.
    """
    return SimpleNamespace(redis=object())


async def test_publishes_one_message_per_committed_snapshot(
    pubsub: FakePubSub, settings: Settings
) -> None:
    await ingest_runtime.publish_committed(
        _container(),
        settings,
        (COMMITTED, COMMITTED),
    )

    assert len(pubsub.published) == 2


async def test_publishes_to_the_configured_channel(pubsub: FakePubSub, settings: Settings) -> None:
    await ingest_runtime.publish_committed(_container(), settings, (COMMITTED,))

    ((channel, _),) = pubsub.published
    assert channel == settings.realtime.snapshot_channel


async def test_prices_cross_as_exact_strings(pubsub: FakePubSub, settings: Settings) -> None:
    """JSON numbers are doubles; a Decimal is not one."""
    await ingest_runtime.publish_committed(_container(), settings, (COMMITTED,))

    ((_, payload),) = pubsub.published
    assert payload["spot"] == "24512.35"
    assert isinstance(payload["spot"], str)


async def test_timestamps_are_rfc3339_with_a_z(pubsub: FakePubSub, settings: Settings) -> None:
    await ingest_runtime.publish_committed(_container(), settings, (COMMITTED,))

    ((_, payload),) = pubsub.published
    assert payload["captured_at"] == "2026-10-09T08:30:00Z"
    assert payload["session_date"] == "2026-10-09"
    assert payload["published_at"].endswith("Z")


async def test_carries_every_field_the_contract_requires(
    pubsub: FakePubSub, settings: Settings
) -> None:
    await ingest_runtime.publish_committed(_container(), settings, (COMMITTED,))

    ((_, payload),) = pubsub.published
    assert {"symbol", "session_date", "captured_at", "source"} <= set(payload)


async def test_publishes_nothing_when_the_tick_wrote_nothing(
    pubsub: FakePubSub, settings: Settings
) -> None:
    await ingest_runtime.publish_committed(_container(), settings, ())

    assert pubsub.published == []


async def test_publishes_nothing_when_realtime_is_disabled(
    pubsub: FakePubSub,
) -> None:
    disabled = Settings(realtime=RealtimeSettings(enabled=False))

    await ingest_runtime.publish_committed(_container(), disabled, (COMMITTED,))

    assert pubsub.published == []


async def test_a_redis_failure_never_propagates(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """The capture loop must outlive a broken Redis."""
    monkeypatch.setattr(ingest_runtime, "RedisPubSub", lambda _redis: FakePubSub(fail=True))

    await ingest_runtime.publish_committed(_container(), settings, (COMMITTED,))


async def test_one_failed_publish_does_not_stop_the_rest(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    class FlakyPubSub(FakePubSub):
        async def publish(self, channel: str, payload: Mapping[str, Any]) -> int:
            if payload["symbol"] == "BANKNIFTY":
                raise ConnectionError("one bad publish")
            self.published.append((channel, payload))
            return 0

    flaky = FlakyPubSub()
    monkeypatch.setattr(ingest_runtime, "RedisPubSub", lambda _redis: flaky)

    await ingest_runtime.publish_committed(
        _container(),
        settings,
        (dataclasses.replace(COMMITTED, symbol="BANKNIFTY"), COMMITTED),
    )

    assert [payload["symbol"] for _, payload in flaky.published] == ["NIFTY"]
