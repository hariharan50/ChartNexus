"""HUGIN's IST cadence helpers — pure boundary tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from marketcompass.contexts.hugin.domain.schedule import (
    SessionWindow,
    is_aligned_tick,
    is_session_open,
    next_wake,
)

_IST = timezone(timedelta(hours=5, minutes=30))
WINDOW = SessionWindow.from_strings("09:15", "15:40")

# 2026-08-24 is a Monday; 2026-08-22 is a Saturday.
MON = lambda h, m: datetime(2026, 8, 24, h, m, tzinfo=_IST)  # noqa: E731
SAT = lambda h, m: datetime(2026, 8, 22, h, m, tzinfo=_IST)  # noqa: E731


def test_session_open_within_hours_on_a_weekday() -> None:
    assert is_session_open(MON(10, 0), WINDOW) is True


def test_session_closed_before_open_and_after_close() -> None:
    assert is_session_open(MON(9, 0), WINDOW) is False
    assert is_session_open(MON(15, 45), WINDOW) is False


def test_session_closed_on_weekend() -> None:
    assert is_session_open(SAT(11, 0), WINDOW) is False


def test_aligned_tick_matches_the_open_minute() -> None:
    assert is_aligned_tick(MON(10, 15), WINDOW) is True
    assert is_aligned_tick(MON(10, 30), WINDOW) is False


def test_next_wake_before_open_is_the_open() -> None:
    assert next_wake(MON(8, 0), WINDOW, 3600) == MON(9, 15)


def test_next_wake_mid_session_snaps_to_next_15_boundary() -> None:
    assert next_wake(MON(10, 20), WINDOW, 3600) == MON(11, 15)


def test_next_wake_after_close_rolls_to_next_trading_day() -> None:
    assert next_wake(MON(16, 0), WINDOW, 3600) == datetime(2026, 8, 25, 9, 15, tzinfo=_IST)


def test_next_wake_on_weekend_rolls_to_monday_open() -> None:
    assert next_wake(SAT(11, 0), WINDOW, 3600) == MON(9, 15)


def test_next_wake_free_running_is_one_interval_from_now() -> None:
    got = next_wake(MON(10, 20), WINDOW, 3600, align_to_open=False)
    assert got == MON(11, 20)


def test_next_wake_accepts_utc_and_returns_ist() -> None:
    utc_now = datetime(2026, 8, 24, 4, 0, tzinfo=UTC)  # 09:30 IST
    assert next_wake(utc_now, WINDOW, 3600) == MON(10, 15)
