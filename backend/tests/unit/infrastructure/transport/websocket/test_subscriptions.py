"""Per-connection subscription state."""

from __future__ import annotations

import pytest

from chartnexus.contexts.realtime_delivery.domain.topics import SNAPSHOTS, Topic
from chartnexus.infrastructure.transport.websocket.subscriptions import (
    SubscriptionSet,
    TopicLimitExceededError,
)

NIFTY = Topic.parse("snapshots:NIFTY")
BANKNIFTY = Topic.parse("snapshots:BANKNIFTY")
EVERYTHING = Topic.parse("snapshots:*")


def test_starts_empty() -> None:
    assert len(SubscriptionSet(limit=8)) == 0


def test_adds_and_removes() -> None:
    subscriptions = SubscriptionSet(limit=8)

    subscriptions.add([NIFTY, BANKNIFTY])
    assert len(subscriptions) == 2

    subscriptions.remove([NIFTY])
    assert NIFTY not in subscriptions
    assert BANKNIFTY in subscriptions


def test_adding_a_held_topic_is_idempotent() -> None:
    """Re-sending the same set after a reconnect must not accumulate."""
    subscriptions = SubscriptionSet(limit=8)

    subscriptions.add([NIFTY])
    subscriptions.add([NIFTY])

    assert len(subscriptions) == 1


def test_removing_a_topic_never_held_is_not_an_error() -> None:
    subscriptions = SubscriptionSet(limit=8)

    subscriptions.remove([NIFTY])

    assert len(subscriptions) == 0


def test_refuses_to_exceed_the_limit() -> None:
    subscriptions = SubscriptionSet(limit=2)

    with pytest.raises(TopicLimitExceededError):
        subscriptions.add([NIFTY, BANKNIFTY, EVERYTHING])


def test_a_refused_add_changes_nothing() -> None:
    """All-or-nothing.

    A half-applied subscribe would leave the client's idea of its own state
    permanently wrong — and since `ack` reports the whole set, the disagreement
    would be invisible until a human noticed a missing stream.
    """
    subscriptions = SubscriptionSet(limit=2)
    subscriptions.add([NIFTY])

    with pytest.raises(TopicLimitExceededError):
        subscriptions.add([BANKNIFTY, EVERYTHING])

    assert subscriptions.as_wire() == ("snapshots:NIFTY",)


def test_re_adding_held_topics_cannot_breach_the_limit() -> None:
    """At the cap, resending the identical set still succeeds."""
    subscriptions = SubscriptionSet(limit=2)
    subscriptions.add([NIFTY, BANKNIFTY])

    subscriptions.add([NIFTY, BANKNIFTY])

    assert len(subscriptions) == 2


class TestMatching:
    def test_finds_an_exact_subscription(self) -> None:
        subscriptions = SubscriptionSet(limit=8)
        subscriptions.add([NIFTY])

        assert subscriptions.matching(SNAPSHOTS, "NIFTY") == NIFTY

    def test_finds_nothing_for_an_unsubscribed_symbol(self) -> None:
        subscriptions = SubscriptionSet(limit=8)
        subscriptions.add([NIFTY])

        assert subscriptions.matching(SNAPSHOTS, "SENSEX") is None

    def test_a_wildcard_entitles_the_connection_to_any_symbol(self) -> None:
        subscriptions = SubscriptionSet(limit=8)
        subscriptions.add([EVERYTHING])

        assert subscriptions.matching(SNAPSHOTS, "SENSEX") == EVERYTHING

    def test_overlapping_subscriptions_match_once(self) -> None:
        """Holding both the symbol and the wildcard must not double-deliver."""
        subscriptions = SubscriptionSet(limit=8)
        subscriptions.add([NIFTY, EVERYTHING])

        assert subscriptions.matching(SNAPSHOTS, "NIFTY") is not None


def test_as_wire_renders_contract_strings() -> None:
    subscriptions = SubscriptionSet(limit=8)
    subscriptions.add([NIFTY, EVERYTHING])

    assert sorted(subscriptions.as_wire()) == ["snapshots:*", "snapshots:NIFTY"]
