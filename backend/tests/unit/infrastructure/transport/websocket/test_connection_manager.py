"""The connection registry and the fan-out.

The behaviour that matters under load is the backpressure policy: a slow
consumer must lose its *oldest* frame and keep running, because every frame is
an invalidation prompt and the newest one is the only one worth having.
"""

from __future__ import annotations

import pytest

from chartnexus.contexts.realtime_delivery.domain.topics import SNAPSHOTS, Topic
from chartnexus.infrastructure.transport.websocket.connection_manager import (
    ConnectionManager,
    ServerFullError,
)

NIFTY = Topic.parse("snapshots:NIFTY")
BANKNIFTY = Topic.parse("snapshots:BANKNIFTY")
EVERYTHING = Topic.parse("snapshots:*")


def _manager(*, queue_size: int = 8, max_connections: int = 10) -> ConnectionManager:
    return ConnectionManager(queue_size=queue_size, max_connections=max_connections, topic_limit=8)


def _drain(connection) -> list[str]:  # type: ignore[no-untyped-def]
    frames = []
    while not connection.outbox.empty():
        frames.append(connection.outbox.get_nowait())
    return frames


class TestRegistry:
    def test_registers_and_counts(self) -> None:
        manager = _manager()

        manager.register(user_id="u1", tenant_id="t1")

        assert manager.open_connections == 1

    def test_each_connection_gets_its_own_id(self) -> None:
        manager = _manager()

        first = manager.register(user_id="u1", tenant_id="t1")
        second = manager.register(user_id="u1", tenant_id="t1")

        assert first.id != second.id

    def test_unregister_frees_the_slot(self) -> None:
        manager = _manager()
        connection = manager.register(user_id="u1", tenant_id="t1")

        manager.unregister(connection)

        assert manager.open_connections == 0

    def test_unregister_is_idempotent(self) -> None:
        """A socket can fail on both the read and the write path; both unwind here."""
        manager = _manager()
        connection = manager.register(user_id="u1", tenant_id="t1")

        manager.unregister(connection)
        manager.unregister(connection)

        assert manager.open_connections == 0

    def test_refuses_past_the_connection_cap(self) -> None:
        manager = _manager(max_connections=1)
        manager.register(user_id="u1", tenant_id="t1")

        with pytest.raises(ServerFullError):
            manager.register(user_id="u2", tenant_id="t2")


class TestFanOut:
    def test_delivers_to_a_subscriber(self) -> None:
        manager = _manager()
        connection = manager.register(user_id="u1", tenant_id="t1")
        connection.subscriptions.add([NIFTY])

        result = manager.fan_out(kind=SNAPSHOTS, symbol="NIFTY", frame="frame-1")

        assert result.delivered == 1
        assert _drain(connection) == ["frame-1"]

    def test_skips_connections_that_did_not_ask(self) -> None:
        manager = _manager()
        subscriber = manager.register(user_id="u1", tenant_id="t1")
        subscriber.subscriptions.add([NIFTY])
        bystander = manager.register(user_id="u2", tenant_id="t2")
        bystander.subscriptions.add([BANKNIFTY])

        manager.fan_out(kind=SNAPSHOTS, symbol="NIFTY", frame="frame-1")

        assert _drain(subscriber) == ["frame-1"]
        assert _drain(bystander) == []

    def test_a_connection_with_no_subscriptions_receives_nothing(self) -> None:
        manager = _manager()
        connection = manager.register(user_id="u1", tenant_id="t1")

        result = manager.fan_out(kind=SNAPSHOTS, symbol="NIFTY", frame="frame-1")

        assert result.is_noop
        assert _drain(connection) == []

    def test_wildcard_subscribers_receive_every_symbol(self) -> None:
        manager = _manager()
        connection = manager.register(user_id="u1", tenant_id="t1")
        connection.subscriptions.add([EVERYTHING])

        manager.fan_out(kind=SNAPSHOTS, symbol="SENSEX", frame="frame-1")

        assert _drain(connection) == ["frame-1"]

    def test_overlapping_subscriptions_deliver_one_frame(self) -> None:
        """Holding both snapshots:NIFTY and snapshots:* is not a double send."""
        manager = _manager()
        connection = manager.register(user_id="u1", tenant_id="t1")
        connection.subscriptions.add([NIFTY, EVERYTHING])

        manager.fan_out(kind=SNAPSHOTS, symbol="NIFTY", frame="frame-1")

        assert _drain(connection) == ["frame-1"]

    def test_no_subscribers_is_a_noop_not_an_error(self) -> None:
        """The normal state with no browser open."""
        result = _manager().fan_out(kind=SNAPSHOTS, symbol="NIFTY", frame="frame-1")

        assert result.is_noop
        assert result.delivered == 0

    def test_delivers_the_same_frame_to_many(self) -> None:
        manager = _manager()
        connections = [manager.register(user_id=f"u{i}", tenant_id="t1") for i in range(5)]
        for connection in connections:
            connection.subscriptions.add([EVERYTHING])

        result = manager.fan_out(kind=SNAPSHOTS, symbol="NIFTY", frame="frame-1")

        assert result.delivered == 5
        assert all(_drain(connection) == ["frame-1"] for connection in connections)


class TestBackpressure:
    def test_drops_the_oldest_frame_when_the_queue_is_full(self) -> None:
        manager = _manager(queue_size=2)
        connection = manager.register(user_id="u1", tenant_id="t1")
        connection.subscriptions.add([NIFTY])

        for index in range(4):
            manager.fan_out(kind=SNAPSHOTS, symbol="NIFTY", frame=f"frame-{index}")

        # The two newest survive; a stale invalidation prompt is worthless.
        assert _drain(connection) == ["frame-2", "frame-3"]

    def test_counts_what_it_dropped(self) -> None:
        """Non-zero at disconnect is the only signal a client was too slow."""
        manager = _manager(queue_size=1)
        connection = manager.register(user_id="u1", tenant_id="t1")
        connection.subscriptions.add([NIFTY])

        for index in range(3):
            manager.fan_out(kind=SNAPSHOTS, symbol="NIFTY", frame=f"frame-{index}")

        assert connection.dropped == 2

    def test_a_slow_consumer_is_reported_as_degraded_not_undelivered(self) -> None:
        manager = _manager(queue_size=1)
        connection = manager.register(user_id="u1", tenant_id="t1")
        connection.subscriptions.add([NIFTY])

        manager.fan_out(kind=SNAPSHOTS, symbol="NIFTY", frame="frame-0")
        result = manager.fan_out(kind=SNAPSHOTS, symbol="NIFTY", frame="frame-1")

        assert result.delivered == 1
        assert result.degraded == 1

    def test_a_slow_consumer_does_not_starve_a_fast_one(self) -> None:
        manager = _manager(queue_size=1)
        slow = manager.register(user_id="slow", tenant_id="t1")
        slow.subscriptions.add([NIFTY])
        fast = manager.register(user_id="fast", tenant_id="t1")
        fast.subscriptions.add([NIFTY])

        manager.fan_out(kind=SNAPSHOTS, symbol="NIFTY", frame="frame-0")
        _drain(fast)  # the fast client reads promptly
        manager.fan_out(kind=SNAPSHOTS, symbol="NIFTY", frame="frame-1")

        assert _drain(fast) == ["frame-1"]
        assert slow.dropped == 1
