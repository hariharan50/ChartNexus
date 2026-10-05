"""Institutional flow arithmetic — nets, running totals and streaks."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from chartnexus.contexts.market_breadth.domain.flows import (
    FlowDay,
    ParticipantFlow,
    Segment,
    SegmentFlow,
    cash_history,
    net_streak,
    window_total,
)

pytestmark = pytest.mark.unit


def cash_day(day: int, *, fii: tuple[str, str], dii: tuple[str, str] | None = None) -> FlowDay:
    segments = [
        SegmentFlow(
            segment=Segment.CASH,
            fii=ParticipantFlow(Decimal(fii[0]), Decimal(fii[1])),
            dii=None if dii is None else ParticipantFlow(Decimal(dii[0]), Decimal(dii[1])),
        )
    ]
    return FlowDay(session_date=date(2026, 9, day), segments=tuple(segments))


def test_net_is_buy_minus_sell() -> None:
    assert ParticipantFlow(Decimal(1200), Decimal(900)).net == Decimal(300)
    assert ParticipantFlow(Decimal(900), Decimal(1200)).net == Decimal(-300)


def test_turnover_adds_both_sides() -> None:
    assert ParticipantFlow(Decimal(1200), Decimal(900)).turnover == Decimal(2100)


def test_cash_history_is_oldest_first_with_running_totals() -> None:
    days = [
        cash_day(3, fii=("1000", "700"), dii=("800", "900")),
        cash_day(1, fii=("500", "900"), dii=("900", "600")),
        cash_day(2, fii=("700", "700"), dii=("600", "600")),
    ]

    history = cash_history(days)

    assert [entry.session_date.day for entry in history] == [1, 2, 3]
    assert [entry.fii_net for entry in history] == [Decimal(-400), Decimal(0), Decimal(300)]
    # Running, not per-day: the third entry carries the whole window.
    assert history[-1].fii_cumulative == Decimal(-100)
    assert history[-1].dii_cumulative == Decimal(200)


def test_a_day_without_a_cash_segment_is_dropped_not_zero_filled() -> None:
    """A session nobody published is not a session in which nobody traded."""
    days = [
        cash_day(1, fii=("500", "400")),
        FlowDay(session_date=date(2026, 9, 2), segments=()),
    ]

    history = cash_history(days)

    assert [entry.session_date.day for entry in history] == [1]


def test_missing_dii_line_reads_as_zero_net_not_as_a_crash() -> None:
    history = cash_history([cash_day(1, fii=("500", "400"))])

    assert history[0].dii_net == Decimal(0)
    assert history[0].dii_buy == Decimal(0)


def test_streak_counts_backwards_and_carries_the_sign() -> None:
    assert net_streak([Decimal(-5), Decimal(3), Decimal(2), Decimal(9)]) == 3
    assert net_streak([Decimal(5), Decimal(-3), Decimal(-2)]) == -2


def test_a_flat_session_breaks_a_streak_rather_than_extending_it() -> None:
    """A day with no net is not a day of buying."""
    assert net_streak([Decimal(3), Decimal(2), Decimal(0)]) == 0
    assert net_streak([Decimal(3), Decimal(0), Decimal(2)]) == 1


def test_streak_of_nothing_is_zero() -> None:
    assert net_streak([]) == 0


def test_window_total_takes_the_most_recent_sessions() -> None:
    values = [Decimal(10), Decimal(20), Decimal(30), Decimal(40)]

    assert window_total(values, 2) == Decimal(70)
    # Shorter history than the window returns what exists, unpadded.
    assert window_total(values, 10) == Decimal(100)
    assert window_total(values, 0) == Decimal(0)
