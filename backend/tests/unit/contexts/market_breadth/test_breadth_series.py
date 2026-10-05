"""Counting a session's breadth out of captured prices.

Every failure mode here draws a perfectly plausible chart. A baseline applied
to the wrong symbol, a member silently dropped when the tape went quiet, the
benchmark counted as one of its own constituents — none of them throws, and
each one moves the line the reader is about to trade off.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from chartnexus.contexts.market_breadth.domain.breadth_series import (
    PricePoint,
    breadth_series,
    within_session,
)

pytestmark = pytest.mark.unit

#: 09:20 IST on 22 September 2026, in UTC.
OPEN = datetime(2026, 9, 22, 3, 50, tzinfo=UTC)
BASELINES = {"A": Decimal(100), "B": Decimal(100), "C": Decimal(100)}


def tick(symbol: str, minute: int, price: str) -> PricePoint:
    return PricePoint(symbol=symbol, at=OPEN + timedelta(minutes=minute), price=Decimal(price))


def test_each_bucket_counts_the_whole_scope() -> None:
    points = breadth_series(
        [tick("A", 0, "101"), tick("B", 0, "99"), tick("C", 0, "100")],
        BASELINES,
        bucket_seconds=60,
    )

    assert len(points) == 1
    assert (points[0].advancing, points[0].declining, points[0].unchanged) == (1, 1, 1)
    assert points[0].net == 0


def test_a_member_that_stopped_printing_keeps_its_last_price() -> None:
    """It has not left the index.

    Counting only what printed in a bucket makes the member total sag wherever
    the tape went quiet, which reads as members leaving the market rather than
    as a contract nobody traded for a minute.
    """
    points = breadth_series(
        [
            tick("A", 0, "101"),
            tick("B", 0, "99"),
            tick("C", 0, "100"),
            # Only A prints in the second minute.
            tick("A", 1, "102"),
        ],
        BASELINES,
        bucket_seconds=60,
    )

    assert len(points) == 2
    second = points[1]
    assert second.advancing + second.declining + second.unchanged == 3


def test_a_symbol_with_no_baseline_is_not_counted_as_flat() -> None:
    """We do not know which way it went, and "unchanged" is a claim."""
    points = breadth_series(
        [tick("A", 0, "101"), tick("Z", 0, "500")],
        {"A": Decimal(100)},
        bucket_seconds=60,
    )

    assert points[0].advancing == 1
    assert points[0].unchanged == 0


def test_the_deadband_keeps_a_tick_from_being_a_direction() -> None:
    points = breadth_series(
        [tick("A", 0, "100.02"), tick("B", 0, "100.5")],
        {"A": Decimal(100), "B": Decimal(100)},
        bucket_seconds=60,
    )

    assert points[0].unchanged == 1  # +0.02%, inside the band
    assert points[0].advancing == 1  # +0.50%, outside it


def test_the_benchmark_supplies_a_level_without_being_counted() -> None:
    """NIFTY is not one of the fifty stocks in NIFTY.

    It rides in the price stream so one query fetches it with the members; it
    stays out of the counts by having no baseline among them.
    """
    points = breadth_series(
        [tick("A", 0, "101"), tick("B", 0, "99"), tick("NIFTY", 0, "23450")],
        BASELINES,
        bucket_seconds=60,
        level_symbol="NIFTY",
    )

    assert points[0].level == Decimal(23450)
    assert points[0].advancing + points[0].declining + points[0].unchanged == 2


def test_weights_ride_alongside_the_counts() -> None:
    """Twelve small names up is not the same as most of the index being up."""
    points = breadth_series(
        [tick("A", 0, "101"), tick("B", 0, "99")],
        {"A": Decimal(100), "B": Decimal(100)},
        bucket_seconds=60,
        weights={"A": Decimal(3), "B": Decimal(40)},
    )

    assert points[0].advancing == 1
    assert points[0].advancing_weight == Decimal(3)
    assert points[0].declining_weight == Decimal(40)


def test_a_scope_with_no_weights_reports_none_rather_than_zero() -> None:
    """Zero weight advancing and no weights at all are different facts."""
    points = breadth_series([tick("A", 0, "101")], BASELINES, bucket_seconds=60)
    assert points[0].advancing_weight is None


def test_buckets_are_stamped_with_an_instant_that_happened() -> None:
    points = breadth_series(
        [tick("A", 0, "101"), tick("A", 4, "102")],
        BASELINES,
        bucket_seconds=900,
    )

    assert len(points) == 1
    assert points[0].at == OPEN + timedelta(minutes=4)


def test_an_empty_capture_draws_nothing() -> None:
    assert breadth_series([], BASELINES, bucket_seconds=60) == []


# -- session clipping ----------------------------------------------------------


def test_prints_after_the_bell_are_dropped() -> None:
    """The broker keeps answering with the last traded price after the close.

    Left in, that tail reads as the market going flat — a statement about the
    market rather than about the capture.
    """
    after_close = datetime(2026, 9, 22, 11, 0, tzinfo=UTC)  # 16:30 IST
    kept = within_session(
        [
            PricePoint(symbol="A", at=OPEN, price=Decimal(100)),
            PricePoint(symbol="A", at=after_close, price=Decimal(100)),
        ],
        open_minute=9 * 60 + 15,
        close_minute=15 * 60 + 30,
        tz_offset_minutes=330,
    )

    assert [point.at for point in kept] == [OPEN]


def test_prints_before_the_open_are_dropped() -> None:
    before_open = datetime(2026, 9, 22, 3, 0, tzinfo=UTC)  # 08:30 IST
    kept = within_session(
        [PricePoint(symbol="A", at=before_open, price=Decimal(100))],
        open_minute=9 * 60 + 15,
        close_minute=15 * 60 + 30,
        tz_offset_minutes=330,
    )

    assert kept == []
