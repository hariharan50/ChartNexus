"""The watch window: weekdays, session hours, and the holidays nobody else models.

Deliberately a copy of the shape in ``contexts/hugin/domain/schedule.py`` rather
than a shared import — bounded contexts may not import each other, and CI
enforces it. The duplication is two dozen lines of calendar arithmetic and is
the sanctioned cost of the boundary.

Two things differ from HUGIN's, and both are the reason this exists separately:

**The window is narrower.** ``MarketSettings.session_close`` is 15:40, because
every existing consumer is derivatives-facing. Level alerts stop at 15:20 — an
alert at 15:38 is not actionable.

**Holidays are modelled.** Every other module in the repo explicitly defers
them, which is fine when a holiday merely yields an empty read. Here it is not:
a watcher running on a holiday sees no ticks during what it believes are market
hours, and the feed-health alarm would page about a dead feed on fifteen
perfectly healthy days a year.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

_LAST_WEEKDAY = 4  # Monday=0 .. Friday=4

#: How far ahead ``next_trading_day`` will look. The longest real NSE
#: closure is a long weekend plus a holiday; 15 days is far past that and
#: still short enough that a bad holiday list raises rather than hangs.
_MAX_CLOSED_RUN = 15


def to_ist(moment: datetime) -> datetime:
    """``moment`` expressed in IST. A naive input is assumed to be UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(IST)


def parse_hhmm(value: str) -> time:
    hour, _, minute = value.partition(":")
    return time(hour=int(hour), minute=int(minute))


@dataclass(frozen=True, slots=True)
class WatchWindow:
    """When the watcher is awake, and which days it skips."""

    open: time
    close: time
    #: Exchange holidays. Empty means weekday-only, matching the rest of the repo.
    holidays: frozenset[date] = frozenset()

    @classmethod
    def from_config(
        cls, open_: str, close: str, holidays: frozenset[date] | None = None
    ) -> WatchWindow:
        window = cls(
            open=parse_hhmm(open_),
            close=parse_hhmm(close),
            holidays=holidays or frozenset(),
        )
        if window.open >= window.close:
            raise ValueError(f"watch window opens at {open_} and closes at {close}")
        return window

    def is_trading_day(self, day: date) -> bool:
        return day.weekday() <= _LAST_WEEKDAY and day not in self.holidays

    def is_open(self, moment: datetime) -> bool:
        """True when ``moment`` is a trading day inside [open, close] in IST."""
        ist = to_ist(moment)
        if not self.is_trading_day(ist.date()):
            return False
        return self.open <= ist.time() <= self.close

    def session_date(self, moment: datetime) -> date:
        """The trading session ``moment`` belongs to.

        Not the calendar date. The boundary is the closing bell, not midnight,
        and it skips forward over weekends and holidays — so 20:00 on Friday
        belongs to Monday's session, and Sunday afternoon does too.

        That matters because of *when levels get marked*. Pivots are computed
        from a close, so the natural time to mark tomorrow's levels is after
        today's — in the evening, or over the weekend. On a midnight boundary
        those marks carry Friday's date, and Monday morning the watcher reads
        them as stale and goes quiet on levels that are in fact exactly the
        ones wanted. Silence on a real break is one of the two failure modes
        this module exists to prevent, so the boundary moves to the bell.

        A moment before the open belongs to that day's session: marking at
        08:50 is marking for the session about to start.

        Used to stamp marks, to key the daily cap, and to decide when a new
        session has begun, so all three agree on where the boundary falls.
        """
        ist = to_ist(moment)
        day = ist.date()
        # Before the bell, today's session is still ahead — but only if today
        # is one. A holiday or a Saturday morning rolls forward like any other
        # closed moment.
        if ist.time() <= self.close and self.is_trading_day(day):
            return day
        return self.next_trading_day(day)

    def next_trading_day(self, day: date) -> date:
        """The first trading day strictly after ``day``.

        Bounded rather than unbounded: a holiday list wide enough to swallow
        two weeks is a misconfiguration, and looping forever on it would hang
        the watcher instead of failing where it can be seen.
        """
        for step in range(1, _MAX_CLOSED_RUN + 1):
            candidate = day + timedelta(days=step)
            if self.is_trading_day(candidate):
                return candidate
        raise ValueError(
            f"no trading day within {_MAX_CLOSED_RUN} days of {day.isoformat()} — "
            "check the configured holiday list"
        )


def parse_holidays(raw: str | list[str] | None) -> frozenset[date]:
    """Read a holiday list from config.

    Accepts a comma-separated string (how an env var arrives) or a list (how a
    structured config arrives). Blank entries are skipped so a trailing comma in
    a hand-edited ``.env`` is not an error — the common case is someone adding
    next year's dates in a hurry, and failing startup over whitespace would be
    the wrong trade.
    """
    if raw is None:
        return frozenset()
    items = raw.split(",") if isinstance(raw, str) else raw
    return frozenset(date.fromisoformat(item.strip()) for item in items if item.strip())
