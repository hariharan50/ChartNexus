"""MME100's pre-market cadence — pure boundary tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from marketcompass.contexts.mme100.domain.schedule import (
    is_trading_day,
    next_briefing_wake,
    parse_hhmm,
)

_IST = timezone(timedelta(hours=5, minutes=30))
BRIEFING = parse_hhmm("08:30")

# 2026-08-24 is a Monday; 2026-08-22 is a Saturday; 2026-08-21 is a Friday.
MON = lambda h, m: datetime(2026, 8, 24, h, m, tzinfo=_IST)  # noqa: E731
SAT = lambda h, m: datetime(2026, 8, 22, h, m, tzinfo=_IST)  # noqa: E731
FRI = lambda h, m: datetime(2026, 8, 21, h, m, tzinfo=_IST)  # noqa: E731


def test_parse_hhmm() -> None:
    t = parse_hhmm("08:30")
    assert (t.hour, t.minute) == (8, 30)


def test_before_todays_slot_returns_today() -> None:
    assert next_briefing_wake(MON(6, 0), BRIEFING) == MON(8, 30)


def test_after_todays_slot_rolls_to_next_weekday() -> None:
    # Monday after 08:30 -> Tuesday 08:30.
    assert next_briefing_wake(MON(9, 0), BRIEFING) == MON(8, 30) + timedelta(days=1)


def test_weekend_rolls_to_monday() -> None:
    assert next_briefing_wake(SAT(9, 0), BRIEFING) == MON(8, 30)


def test_friday_after_slot_skips_weekend_to_monday() -> None:
    assert next_briefing_wake(FRI(9, 0), BRIEFING) == MON(8, 30)


def test_is_trading_day() -> None:
    assert is_trading_day(MON(8, 30).date()) is True
    assert is_trading_day(SAT(8, 30).date()) is False
