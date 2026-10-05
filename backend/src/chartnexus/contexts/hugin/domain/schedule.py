"""IST cadence helpers for the HUGIN worker — pure and unit-testable.

The worker wakes on the hour during the trading session. These helpers answer the
three questions it asks each loop: is the session open now, is this an aligned
tick boundary, and when is the next wake? The session window is passed in (built
by the worker from ``MarketSettings.session_open``/``session_close``) so the
domain stays free of settings/infra.

India observes no DST, so a fixed +05:30 offset is correct — the same constant the
ingest loop and the STRYX journal use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone

_IST = timezone(timedelta(hours=5, minutes=30))
# A weekday check is the only calendar HUGIN needs; exchange holidays are out of
# scope (a holiday simply yields empty/mock reads, which the cycle survives).
_LAST_WEEKDAY = 4  # Monday=0 .. Friday=4
_MAX_LOOKAHEAD_DAYS = 8  # bounds next_wake's search across a long weekend/holiday.


@dataclass(frozen=True, slots=True)
class SessionWindow:
    """The trading session's open/close wall-clock times, in IST."""

    open: time
    close: time

    @classmethod
    def from_strings(cls, open_: str, close: str) -> SessionWindow:
        return cls(open=_parse_hhmm(open_), close=_parse_hhmm(close))


def _parse_hhmm(value: str) -> time:
    hour, _, minute = value.partition(":")
    return time(hour=int(hour), minute=int(minute))


def to_ist(now: datetime) -> datetime:
    """The instant expressed in IST (accepts naive-UTC or any aware datetime)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(_IST)


def is_trading_day(day: date) -> bool:
    return day.weekday() <= _LAST_WEEKDAY


def is_session_open(now: datetime, window: SessionWindow) -> bool:
    """True when ``now`` falls on a weekday within [open, close] in IST."""
    ist = to_ist(now)
    return (
        is_trading_day(ist.date())
        and window.open <= ist.timetz().replace(tzinfo=None) <= window.close
    )


def is_aligned_tick(now: datetime, window: SessionWindow) -> bool:
    """True when ``now`` sits on a :MM boundary matching the session open minute.

    HUGIN's ticks fall on the open minute of each hour (09:15, 10:15, …), so a
    wake whose IST minute equals the open minute is an aligned tick.
    """
    return to_ist(now).minute == window.open.minute


def next_wake(
    now: datetime,
    window: SessionWindow,
    interval_seconds: int,
    *,
    align_to_open: bool = True,
) -> datetime:
    """The next tick strictly after ``now`` (IST, tz-aware).

    With ``align_to_open`` the ticks are ``open, open+interval, …`` up to close;
    otherwise the first wake is the open and thereafter it free-runs on the
    interval within the session. Outside the session it returns the next trading
    day's open.
    """
    ist = to_ist(now)
    interval = timedelta(seconds=interval_seconds)

    day = ist.date()
    for _ in range(_MAX_LOOKAHEAD_DAYS):
        if is_trading_day(day):
            open_dt = datetime.combine(day, window.open, tzinfo=_IST)
            close_dt = datetime.combine(day, window.close, tzinfo=_IST)
            if ist < open_dt:
                return open_dt
            if ist <= close_dt:
                if not align_to_open:
                    # Free-running: one interval from now, not snapped to the grid.
                    candidate = ist + interval
                    if candidate <= close_dt:
                        return candidate
                else:
                    tick = open_dt
                    while tick <= close_dt:
                        if tick > ist:
                            return tick
                        tick += interval
                # Past the last in-session tick — fall through to the next day.
        day = day + timedelta(days=1)

    # Unreachable in practice (a trading day always exists within a week), but a
    # deterministic fallback beats raising inside the loop.
    return datetime.combine(day, window.open, tzinfo=_IST)
