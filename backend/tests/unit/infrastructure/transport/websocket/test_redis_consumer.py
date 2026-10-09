"""The Redis-to-sockets bridge.

The publisher is a separate process that deploys independently, so the rule
under test is containment: a malformed event costs one event, never the loop.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from typing import Any

from chartnexus.contexts.realtime_delivery.domain.topics import Topic
from chartnexus.infrastructure.transport.websocket.connection_manager import ConnectionManager
from chartnexus.infrastructure.transport.websocket.redis_consumer import run_snapshot_consumer

EVERYTHING = Topic.parse("snapshots:*")

VALID_EVENT = {
    "symbol": "NIFTY",
    "session_date": "2026-10-09",
    "captured_at": "2026-10-09T08:30:00Z",
    "source": "mock",
    "spot": "24500.50",
    "expiry": "2026-10-14",
    "published_at": "2026-10-09T08:30:01Z",
}


class FakeSubscription:
    def __init__(self, events: list[Mapping[str, Any]]) -> None:
        self._events = events

    async def events(self, *, stop: asyncio.Event) -> AsyncIterator[Mapping[str, Any]]:
        for event in self._events:
            yield event
        stop.set()


class FakePubSub:
    """Replays a fixed list of events, then ends the loop."""

    def __init__(self, events: list[Mapping[str, Any]]) -> None:
        self._events = events
        self.subscribed_to: str | None = None

    def subscription(self, channel: str) -> Any:
        self.subscribed_to = channel

        class _Ctx:
            def __init__(self, events: list[Mapping[str, Any]]) -> None:
                self._events = events

            async def __aenter__(self) -> FakeSubscription:
                return FakeSubscription(self._events)

            async def __aexit__(self, *_: object) -> None:
                return None

        return _Ctx(self._events)


async def _run(events: list[Mapping[str, Any]]) -> tuple[ConnectionManager, Any]:
    manager = ConnectionManager(queue_size=16, max_connections=4, topic_limit=4)
    connection = manager.register(user_id="u1", tenant_id="t1")
    connection.subscriptions.add([EVERYTHING])

    await run_snapshot_consumer(
        pubsub=FakePubSub(events),  # type: ignore[arg-type]
        connections=manager,
        channel="rt:snapshots",
        stop=asyncio.Event(),
    )
    return manager, connection


def _frames(connection: Any) -> list[dict[str, Any]]:
    frames = []
    while not connection.outbox.empty():
        frames.append(json.loads(connection.outbox.get_nowait()))
    return frames


class TestDelivery:
    async def test_turns_an_event_into_a_snapshot_frame(self) -> None:
        _, connection = await _run([VALID_EVENT])

        (frame,) = _frames(connection)
        assert frame["type"] == "snapshot_committed"
        assert frame["topic"] == "snapshots:NIFTY"
        assert frame["published_at"] == "2026-10-09T08:30:01Z"
        assert frame["payload"]["spot"] == "24500.50"

    async def test_wildcard_subscribers_are_told_the_concrete_topic(self) -> None:
        """So a client never has to reverse the match to learn which symbol moved."""
        _, connection = await _run([{**VALID_EVENT, "symbol": "SENSEX"}])

        (frame,) = _frames(connection)
        assert frame["topic"] == "snapshots:SENSEX"

    async def test_falls_back_to_captured_at_when_published_at_is_absent(self) -> None:
        event = {key: value for key, value in VALID_EVENT.items() if key != "published_at"}

        _, connection = await _run([event])

        (frame,) = _frames(connection)
        assert frame["published_at"] == VALID_EVENT["captured_at"]

    async def test_optional_fields_may_be_missing(self) -> None:
        event = {key: value for key, value in VALID_EVENT.items() if key not in {"spot", "expiry"}}

        _, connection = await _run([event])

        (frame,) = _frames(connection)
        assert frame["payload"]["spot"] is None
        assert frame["payload"]["expiry"] is None

    async def test_subscribes_to_the_configured_channel(self) -> None:
        pubsub = FakePubSub([])
        manager = ConnectionManager(queue_size=4, max_connections=1, topic_limit=1)

        await run_snapshot_consumer(
            pubsub=pubsub,  # type: ignore[arg-type]
            connections=manager,
            channel="rt:snapshots",
            stop=asyncio.Event(),
        )

        assert pubsub.subscribed_to == "rt:snapshots"


class TestContainment:
    async def test_an_event_missing_a_required_field_is_skipped(self) -> None:
        broken = {key: value for key, value in VALID_EVENT.items() if key != "session_date"}

        _, connection = await _run([broken])

        assert _frames(connection) == []

    async def test_an_unroutable_symbol_is_skipped(self) -> None:
        """Lower case, or punctuation — no client could have subscribed to it."""
        _, connection = await _run([{**VALID_EVENT, "symbol": "nifty"}])

        assert _frames(connection) == []

    async def test_a_bad_event_does_not_stop_the_ones_after_it(self) -> None:
        """The containment guarantee: one bad event, not one dead process."""
        _, connection = await _run(
            [
                {**VALID_EVENT, "symbol": "nifty"},  # unroutable
                {"nonsense": True},  # incomplete
                VALID_EVENT,  # must still arrive
            ]
        )

        (frame,) = _frames(connection)
        assert frame["payload"]["symbol"] == "NIFTY"

    async def test_an_event_nobody_subscribed_to_is_harmless(self) -> None:
        manager = ConnectionManager(queue_size=4, max_connections=2, topic_limit=4)
        connection = manager.register(user_id="u1", tenant_id="t1")
        connection.subscriptions.add([Topic.parse("snapshots:BANKNIFTY")])

        await run_snapshot_consumer(
            pubsub=FakePubSub([VALID_EVENT]),  # type: ignore[arg-type]
            connections=manager,
            channel="rt:snapshots",
            stop=asyncio.Event(),
        )

        assert _frames(connection) == []
