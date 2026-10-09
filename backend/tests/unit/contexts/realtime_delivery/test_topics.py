"""The subscription grammar.

A topic string is a public contract — it appears in client code, in logs and in
``contracts/websocket/v1/`` — so the parser's strictness is behaviour worth
pinning, not an implementation detail.
"""

from __future__ import annotations

import pytest

from chartnexus.contexts.realtime_delivery.domain.topics import (
    SNAPSHOTS,
    Topic,
    snapshots_for,
)
from chartnexus.shared_kernel.domain.errors import ValidationError


class TestParsing:
    def test_parses_a_symbol_topic(self) -> None:
        topic = Topic.parse("snapshots:NIFTY")

        assert topic.kind == SNAPSHOTS
        assert topic.selector == "NIFTY"
        assert not topic.is_wildcard

    def test_parses_the_wildcard(self) -> None:
        topic = Topic.parse("snapshots:*")

        assert topic.is_wildcard

    def test_round_trips_through_its_wire_form(self) -> None:
        assert str(Topic.parse("snapshots:BANKNIFTY")) == "snapshots:BANKNIFTY"

    @pytest.mark.parametrize(
        "raw",
        [
            "snapshots",  # no separator at all
            "",
            "quotes:NIFTY",  # a stream this server does not publish
            "snapshots:nifty",  # lower case; the catalog is upper
            "snapshots:NIFTY-24",  # punctuation
            "snapshots:",  # empty selector
            "snapshots:N IFTY",  # whitespace
        ],
    )
    def test_refuses_anything_else(self, raw: str) -> None:
        with pytest.raises(ValidationError):
            Topic.parse(raw)

    def test_does_not_quietly_upper_case(self) -> None:
        """A lower-case symbol is a client bug worth surfacing.

        Normalising it here would make the same client work against the socket
        and fail against the REST surface it pairs with, which is a far harder
        bug to find than a rejected subscription.
        """
        with pytest.raises(ValidationError):
            Topic.parse("snapshots:nifty")


class TestMatching:
    def test_exact_topic_matches_only_its_symbol(self) -> None:
        topic = Topic.parse("snapshots:NIFTY")

        assert topic.matches(SNAPSHOTS, "NIFTY")
        assert not topic.matches(SNAPSHOTS, "BANKNIFTY")

    def test_wildcard_matches_every_symbol(self) -> None:
        topic = Topic.parse("snapshots:*")

        assert topic.matches(SNAPSHOTS, "NIFTY")
        assert topic.matches(SNAPSHOTS, "SENSEX")

    def test_kind_must_agree_even_for_the_wildcard(self) -> None:
        assert not Topic.parse("snapshots:*").matches("quotes", "NIFTY")

    def test_a_symbol_prefix_is_not_a_match(self) -> None:
        """NIFTY must not receive NIFTYNXT50's events.

        Matching is equality, not ``startswith`` — the catalog is full of
        symbols that share a prefix (NIFTY, NIFTYNXT50, NIFTYFPI), so a prefix
        match would silently cross the streams.
        """
        assert not Topic.parse("snapshots:NIFTY").matches(SNAPSHOTS, "NIFTYNXT50")


class TestSnapshotsFor:
    def test_builds_the_concrete_delivery_topic(self) -> None:
        assert str(snapshots_for("SENSEX")) == "snapshots:SENSEX"

    def test_refuses_a_symbol_the_grammar_cannot_express(self) -> None:
        with pytest.raises(ValidationError):
            snapshots_for("not a symbol")


def test_topics_are_value_objects() -> None:
    """Equality and hashing by value, so a set de-duplicates subscriptions."""
    assert Topic.parse("snapshots:NIFTY") == Topic.parse("snapshots:NIFTY")
    assert len({Topic.parse("snapshots:NIFTY"), Topic.parse("snapshots:NIFTY")}) == 1
