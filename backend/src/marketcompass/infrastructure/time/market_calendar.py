"""Exchange session hours.

Answers "is the market open right now", so a flat tape can be explained as a
closed session rather than a broken feed.

Weekends and session times only. Trading holidays are published annually by the
exchange and are not derivable — a holiday list belongs in the instrument
catalog, loaded from data, and this class will take it as an injected set when
that lands. Until then it will say "open" on Republic Day, which is a known
limitation rather than a hidden one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

_SATURDAY = 5


@dataclass(frozen=True, slots=True)
class ExchangeCalendar:
    """Implements the ``MarketCalendar`` port."""

    timezone: str = "Asia/Kolkata"
    session_open: str = "09:15"
    session_close: str = "15:40"
    holidays: frozenset[date] = field(default_factory=frozenset)

    @property
    def opens_at(self) -> str:
        return self.session_open

    @property
    def closes_at(self) -> str:
        return self.session_close

    def is_open(self, moment: datetime) -> bool:
        local = self._to_exchange_time(moment)

        if local.weekday() >= _SATURDAY:
            return False
        if local.date() in self.holidays:
            return False

        return self._parse(self.session_open) <= local.time() <= self._parse(self.session_close)

    def _to_exchange_time(self, moment: datetime) -> datetime:
        """Interpret a naive datetime as already exchange-local."""
        zone = ZoneInfo(self.timezone)
        if moment.tzinfo is None:
            return moment.replace(tzinfo=zone)
        return moment.astimezone(zone)

    @staticmethod
    def _parse(value: str) -> time:
        hour, _, minute = value.partition(":")
        return time(hour=int(hour), minute=int(minute or 0))
