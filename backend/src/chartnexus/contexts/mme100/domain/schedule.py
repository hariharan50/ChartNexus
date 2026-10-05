"""IST cadence helpers for the MME100 pre-market worker — pure and unit-testable.

Unlike HUGIN (which wakes hourly through the session), MME100 fires **once per
trading day** at a fixed pre-market time (default 08:30 IST, before the 09:15
open). The worker asks one question each loop: when is the next briefing due?
:func:`next_briefing_wake` answers it, always returning a weekday instant strictly
after ``now``.

India observes no DST, so a fixed +05:30 offset is correct — the same constant the
HUGIN loop, the ingest loop and the STRYX journal use.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone

_IST = timezone(timedelta(hours=5, minutes=30))
_LAST_WEEKDAY = 4  # Monday=0 .. Friday=4
_MAX_LOOKAHEAD_DAYS = 8  # bounds the search across a long weekend.


def parse_hhmm(value: str) -> time:
    hour, _, minute = value.partition(":")
    return time(hour=int(hour), minute=int(minute))


def to_ist(now: datetime) -> datetime:
    """The instant expressed in IST (accepts naive-UTC or any aware datetime)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(_IST)


def is_trading_day(day: date) -> bool:
    return day.weekday() <= _LAST_WEEKDAY


def next_briefing_wake(now: datetime, briefing_time: time) -> datetime:
    """The next pre-market briefing instant strictly after ``now`` (IST, tz-aware).

    Today's slot if it is still a weekday and hasn't passed; otherwise the next
    trading day's slot. Weekends and (implicitly) any non-weekday roll forward.
    """
    ist = to_ist(now)
    day = ist.date()
    for _ in range(_MAX_LOOKAHEAD_DAYS):
        if is_trading_day(day):
            slot = datetime.combine(day, briefing_time, tzinfo=_IST)
            if slot > ist:
                return slot
        day = day + timedelta(days=1)

    # Unreachable in practice (a weekday always exists within a week); a
    # deterministic fallback beats raising inside the loop.
    return datetime.combine(day, briefing_time, tzinfo=_IST)
