"""``ExchangeCalendar.next_open`` — when the bell next rings.

The open-interest sweep keeps its closing readings exactly this long, so an
off-by-a-day here either blanks the board overnight or lets one session's
figures run into the next.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from chartnexus.infrastructure.time.market_calendar import ExchangeCalendar

pytestmark = pytest.mark.unit

IST = ZoneInfo("Asia/Kolkata")
CALENDAR = ExchangeCalendar()


def _ist(day: int, hour: int, minute: int = 0) -> datetime:
    # November 2026: the 16th is a Monday.
    return datetime(2026, 11, day, hour, minute, tzinfo=IST)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        pytest.param(_ist(18, 8, 0), _ist(18, 9, 15), id="weekday-before-open-is-today"),
        pytest.param(_ist(18, 10, 0), _ist(19, 9, 15), id="weekday-in-session-is-tomorrow"),
        pytest.param(_ist(18, 16, 0), _ist(19, 9, 15), id="weekday-evening-is-tomorrow"),
        pytest.param(_ist(18, 9, 15), _ist(19, 9, 15), id="at-the-bell-is-strictly-after"),
        pytest.param(_ist(20, 16, 0), _ist(23, 9, 15), id="friday-evening-is-monday"),
        pytest.param(_ist(21, 12, 0), _ist(23, 9, 15), id="saturday-is-monday"),
        pytest.param(_ist(22, 23, 59), _ist(23, 9, 15), id="sunday-night-is-monday"),
    ],
)
def test_the_next_open(moment: datetime, expected: datetime) -> None:
    assert CALENDAR.next_open(moment) == expected


def test_a_utc_moment_is_read_in_exchange_time() -> None:
    # 22:00 UTC on Wednesday is 03:30 IST on Thursday — before Thursday's open.
    assert CALENDAR.next_open(datetime(2026, 11, 18, 22, 0, tzinfo=UTC)) == _ist(19, 9, 15)


def test_listed_holidays_are_skipped() -> None:
    calendar = ExchangeCalendar(holidays=frozenset({date(2026, 11, 19), date(2026, 11, 20)}))
    assert calendar.next_open(_ist(18, 16, 0)) == _ist(23, 9, 15)


def test_the_next_open_is_never_a_moment_the_market_is_closed() -> None:
    for moment in (_ist(18, 16, 0), _ist(20, 16, 0), _ist(21, 12, 0)):
        assert CALENDAR.is_open(CALENDAR.next_open(moment))
