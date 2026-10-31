"""Where one trading session ends and the next begins.

This is the arithmetic that decides whether a morning is quiet because nothing
happened or because the watcher thinks your levels are yesterday's. It gets its
own file because the boundary is not midnight, and every reason it is not is a
case below.

The anchoring facts: in 2026, 26 October is a Monday and 30 October a Friday.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from chartnexus.contexts.trade_buddy.domain.schedule import IST, WatchWindow, to_ist

pytestmark = pytest.mark.unit

MONDAY = date(2026, 10, 26)
FRIDAY = date(2026, 10, 30)
SATURDAY = date(2026, 10, 31)
SUNDAY = date(2026, 11, 1)
NEXT_MONDAY = date(2026, 11, 2)


@pytest.fixture
def window() -> WatchWindow:
    return WatchWindow.from_config("09:15", "15:20")


def ist(day: date, hhmm: str) -> datetime:
    hour, _, minute = hhmm.partition(":")
    return datetime.combine(day, time(int(hour), int(minute)), tzinfo=IST)


class TestInsideTheSession:
    @pytest.mark.parametrize("clock", ["09:15", "12:00", "15:20"])
    def test_a_moment_in_the_window_belongs_to_that_day(self, window, clock):
        assert window.session_date(ist(MONDAY, clock)) == MONDAY

    def test_before_the_open_still_belongs_to_the_session_about_to_start(self, window):
        """Marking at 08:50 is marking for today, not tomorrow."""
        assert window.session_date(ist(MONDAY, "08:50")) == MONDAY

    def test_midnight_belongs_to_the_day_that_is_starting(self, window):
        assert window.session_date(ist(MONDAY, "00:01")) == MONDAY


class TestAfterTheBell:
    """The boundary that makes evening preparation work.

    Pivots come from a close, so levels get marked *after* one — in the
    evening, or over the weekend. On a midnight boundary those marks would
    carry today's date and read as stale tomorrow morning, and the watcher
    would go quiet on exactly the levels that were wanted.
    """

    def test_an_evening_mark_is_for_tomorrow(self, window):
        assert window.session_date(ist(MONDAY, "20:00")) == date(2026, 10, 27)

    def test_the_rollover_is_the_closing_bell(self, window):
        # One minute either side of 15:20.
        assert window.session_date(ist(MONDAY, "15:20")) == MONDAY
        assert window.session_date(ist(MONDAY, "15:21")) == date(2026, 10, 27)

    def test_friday_evening_is_for_monday(self, window):
        """Not Saturday. A session date must be a day that trades."""
        assert window.session_date(ist(FRIDAY, "18:00")) == NEXT_MONDAY

    @pytest.mark.parametrize("day", [SATURDAY, SUNDAY])
    @pytest.mark.parametrize("clock", ["09:00", "14:00", "22:00"])
    def test_the_whole_weekend_is_for_monday(self, window, day, clock):
        """Including Saturday morning, which is before 15:20 but trades nothing."""
        assert window.session_date(ist(day, clock)) == NEXT_MONDAY


class TestHolidays:
    def test_an_evening_before_a_holiday_skips_it(self):
        window = WatchWindow.from_config("09:15", "15:20", frozenset({date(2026, 10, 27)}))
        assert window.session_date(ist(MONDAY, "19:00")) == date(2026, 10, 28)

    def test_a_holiday_itself_rolls_forward_all_day(self):
        holiday = date(2026, 10, 27)
        window = WatchWindow.from_config("09:15", "15:20", frozenset({holiday}))
        # 10:00 on a holiday is inside the clock window but trades nothing, so
        # it belongs to the next session rather than to a session that is not
        # happening.
        assert window.session_date(ist(holiday, "10:00")) == date(2026, 10, 28)

    def test_a_holiday_adjoining_a_weekend_skips_the_whole_run(self):
        window = WatchWindow.from_config("09:15", "15:20", frozenset({NEXT_MONDAY}))
        assert window.session_date(ist(FRIDAY, "18:00")) == date(2026, 11, 3)

    def test_an_absurd_holiday_list_raises_instead_of_hanging(self):
        """A bad config should fail where someone can see it."""
        window = WatchWindow.from_config(
            "09:15",
            "15:20",
            frozenset(date(2026, 11, d) for d in range(1, 30)),
        )
        with pytest.raises(ValueError, match="holiday list"):
            window.session_date(ist(date(2026, 10, 30), "18:00"))


class TestItAgreesWithIsOpen:
    """Both answers come from the same window, so they must not disagree.

    If `is_open` says the market is open while `session_date` has already
    rolled to tomorrow, every level reads as stale mid-session — alerts stop
    with the market still trading, which is the worst outcome in the module.
    """

    @pytest.mark.parametrize("clock", ["09:15", "11:30", "15:19", "15:20"])
    def test_while_the_market_is_open_the_session_is_today(self, window, clock):
        moment = ist(MONDAY, clock)
        assert window.is_open(moment)
        assert window.session_date(moment) == to_ist(moment).date()

    def test_a_session_date_is_always_a_trading_day(self, window):
        """Every minute of a fortnight, including both weekends."""
        start = datetime(2026, 10, 26, tzinfo=IST)
        for minutes in range(0, 14 * 24 * 60, 7):
            moment = start + timedelta(minutes=minutes)
            assert window.is_trading_day(window.session_date(moment))
