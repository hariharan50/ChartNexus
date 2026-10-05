"""The overnight handoff maths.

These are the sums the GIA page's whole claim rests on, so the cases here are
the ones that would be silently wrong rather than obviously broken: a band
drawn a day out of place, a US session that falls off the end of the window
after the Indian close, a composite that reads the same in March and November
because someone baked an IST offset into a US session.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from chartnexus.contexts.global_markets.domain.handoff import (
    Agreement,
    BandState,
    GapSignal,
    PressureBand,
    agreement,
    gap_pressure,
    gap_signal,
    implied_open,
    nifty_is_trading,
    overnight_window,
    region_rollup,
    session_bands,
)
from chartnexus.contexts.global_markets.domain.markets import (
    BY_KEY,
    IST,
    MARKETS,
    session_window,
)
from chartnexus.contexts.global_markets.domain.quotes import (
    DataSource,
    GlobalQuote,
    Provenance,
    QuoteSet,
)

pytestmark = pytest.mark.unit


def ist(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=IST)


def quote(
    key: str,
    change_percent: str,
    price: str = "100",
    previous_close: str | None = None,
    session: datetime | None = None,
) -> GlobalQuote:
    return GlobalQuote(
        key=key,
        price=Decimal(price),
        change=Decimal("1"),
        change_percent=Decimal(change_percent),
        previous_close=Decimal(previous_close if previous_close is not None else price),
        session=session,
        provenance=Provenance(source=DataSource.LIVE, fetched_at=ist(2026, 9, 24, 8)),
    )


def quotes(**moves: str) -> QuoteSet:
    return QuoteSet(
        quotes={key: quote(key, value) for key, value in moves.items()},
        source=DataSource.LIVE,
    )


# -- the window ---------------------------------------------------------------


class TestOvernightWindow:
    def test_before_the_close_the_window_explains_this_mornings_open(self) -> None:
        """At 11:00 a trader wants what drove the session they are trading."""
        window = overnight_window(ist(2026, 9, 24, 11))

        assert window.target_session == date(2026, 9, 24)
        assert window.opened_at == ist(2026, 9, 23, 15, 30)
        assert window.closes_at == ist(2026, 9, 24, 9, 15)

    def test_after_the_close_the_baton_has_been_passed_again(self) -> None:
        """The regression this guards is the expensive one.

        A window still pinned to this morning at 23:00 would place the live New
        York session - the loudest input the page has - outside its own axis,
        and the composite would score the night with the US missing entirely.
        """
        window = overnight_window(ist(2026, 9, 24, 23))

        assert window.target_session == date(2026, 9, 25)
        assert window.opened_at == ist(2026, 9, 24, 15, 30)

    def test_friday_evening_targets_monday(self) -> None:
        # 2026-09-25 is a Friday.
        window = overnight_window(ist(2026, 9, 25, 20))

        assert window.target_session == date(2026, 9, 28)

    def test_a_monday_morning_window_opens_at_fridays_close(self) -> None:
        window = overnight_window(ist(2026, 9, 28, 8))

        assert window.opened_at == ist(2026, 9, 25, 15, 30)

    def test_progress_is_clamped_to_the_window(self) -> None:
        window = overnight_window(ist(2026, 9, 24, 8))

        assert window.progress(ist(2026, 9, 23, 10)) == 0.0
        assert window.progress(ist(2026, 9, 25, 10)) == 1.0
        assert 0.0 < window.progress(ist(2026, 9, 24, 2)) < 1.0


# -- session geometry ---------------------------------------------------------


class TestSessionWindow:
    def test_new_york_is_converted_through_its_own_timezone(self) -> None:
        """September is EDT (UTC-4), so 09:30 New York is 19:00 IST."""
        opens_at, closes_at = session_window(BY_KEY["SPX"], date(2026, 9, 24))

        assert (opens_at.hour, opens_at.minute) == (19, 0)
        assert (closes_at.hour, closes_at.minute) == (1, 30)
        assert closes_at.date() == date(2026, 9, 25)

    def test_the_same_session_shifts_an_hour_once_new_york_leaves_dst(self) -> None:
        """The reason these hours are not stored in IST.

        India does not observe daylight saving and the US does, so a hardcoded
        "US opens 19:00 IST" is wrong for roughly half the calendar. In
        January, EST is UTC-5 and the open lands at 20:00 IST.
        """
        summer, _ = session_window(BY_KEY["SPX"], date(2026, 9, 24))
        winter, _ = session_window(BY_KEY["SPX"], date(2026, 1, 15))

        assert (summer.hour, summer.minute) == (19, 0)
        assert (winter.hour, winter.minute) == (20, 0)

    def test_london_shifts_too(self) -> None:
        summer, _ = session_window(BY_KEY["FTSE"], date(2026, 9, 24))
        winter, _ = session_window(BY_KEY["FTSE"], date(2026, 1, 15))

        assert (summer.hour, summer.minute) == (12, 30)  # BST
        assert (winter.hour, winter.minute) == (13, 30)  # GMT

    def test_tokyo_never_shifts(self) -> None:
        """Japan has no daylight saving, so both dates agree."""
        summer, _ = session_window(BY_KEY["NIKKEI"], date(2026, 9, 24))
        winter, _ = session_window(BY_KEY["NIKKEI"], date(2026, 1, 15))

        assert (summer.hour, summer.minute) == (5, 30)
        assert (winter.hour, winter.minute) == (5, 30)


class TestSessionBands:
    def test_bands_are_ordered_by_when_the_baton_arrives(self) -> None:
        window = overnight_window(ist(2026, 9, 24, 8))
        bands = session_bands(window, quotes(SPX="-0.75"), ist(2026, 9, 24, 8))

        regions = [band.region for band in bands]
        # Europe runs into the Indian evening, the US overnight, Asia at dawn.
        assert regions.index("europe") < regions.index("americas")
        assert regions.index("americas") < regions.index("asia")

    def test_the_us_session_lands_inside_the_window_not_a_day_out(self) -> None:
        window = overnight_window(ist(2026, 9, 24, 8))
        bands = {band.key: band for band in session_bands(window, quotes(), ist(2026, 9, 24, 8))}

        spx = bands["SPX"]
        assert spx.opens_at == ist(2026, 9, 23, 19, 0)
        assert window.opened_at <= spx.opens_at < window.closes_at

    def test_a_band_reports_whether_it_has_run_yet(self) -> None:
        window = overnight_window(ist(2026, 9, 24, 8))
        # 08:00 IST: New York shut hours ago, Tokyo is trading.
        bands = {band.key: band for band in session_bands(window, quotes(), ist(2026, 9, 24, 8))}

        assert bands["SPX"].state is BandState.CLOSED
        assert bands["NIKKEI"].state is BandState.LIVE

    def test_fractions_stay_inside_the_axis(self) -> None:
        window = overnight_window(ist(2026, 9, 24, 8))
        for band in session_bands(window, quotes(), ist(2026, 9, 24, 8)):
            assert 0.0 <= band.start_fraction <= 1.0
            assert 0.0 <= band.end_fraction <= 1.0
            assert band.start_fraction <= band.end_fraction


# -- the composite ------------------------------------------------------------


class TestGapPressure:
    def test_a_red_night_scores_negative_and_a_green_one_positive(self) -> None:
        window = overnight_window(ist(2026, 9, 24, 8))
        now = ist(2026, 9, 24, 8)

        red = gap_pressure(window, quotes(SPX="-1.2", NASDAQ="-1.5", DAX="-0.6"), now)
        green = gap_pressure(window, quotes(SPX="1.2", NASDAQ="1.5", DAX="0.6"), now)

        assert red.score < 0
        assert green.score > 0
        assert red.band in (PressureBand.DOWN, PressureBand.STRONG_DOWN)

    def test_the_contributions_sum_to_the_score(self) -> None:
        """The waterfall has to reconcile with the gauge above it.

        If these ever diverge the page is showing a breakdown of a number it
        did not compute, which is worse than showing no breakdown at all.
        """
        window = overnight_window(ist(2026, 9, 24, 8))
        pressure = gap_pressure(
            window, quotes(SPX="-1.2", NASDAQ="-0.9", NIKKEI="0.4", VIX="5.0"), ist(2026, 9, 24, 8)
        )

        total = sum((item.points for item in pressure.contributions), Decimal("0"))
        assert total == pressure.score

    def test_a_vix_spike_pulls_the_composite_down(self) -> None:
        """VIX is the one inverted weight; flipping its sign would be invisible."""
        window = overnight_window(ist(2026, 9, 24, 8))
        pressure = gap_pressure(window, quotes(VIX="8.0"), ist(2026, 9, 24, 8))

        assert pressure.score < 0

    def test_a_market_that_closed_long_ago_counts_for_less(self) -> None:
        """The piece a flat quote table cannot express.

        The same S&P move is worth more to a 02:00 reader, minutes after the
        New York close, than to an 09:00 reader twenty minutes before the
        Indian open.
        """
        window = overnight_window(ist(2026, 9, 24, 8))
        fresh = gap_pressure(window, quotes(SPX="-1.0"), ist(2026, 9, 24, 2))
        stale = gap_pressure(window, quotes(SPX="-1.0"), ist(2026, 9, 24, 9))

        assert abs(stale.score) < abs(fresh.score)

    def test_recency_never_decays_to_nothing(self) -> None:
        """The US close is old news by the Indian open and still the loudest
        input there is, so the decay flattens rather than reaching zero."""
        window = overnight_window(ist(2026, 9, 24, 8))
        pressure = gap_pressure(window, quotes(SPX="-1.0"), ist(2026, 9, 24, 9, 14))

        assert pressure.contributions[0].recency >= Decimal("0.35")

    def test_missing_markets_are_named_rather_than_silently_dropped(self) -> None:
        """A composite from two of nine inputs is a different claim from one
        built on all nine, and the page has to be able to say so."""
        window = overnight_window(ist(2026, 9, 24, 8))
        pressure = gap_pressure(window, quotes(SPX="-1.0"), ist(2026, 9, 24, 8))

        assert "NASDAQ" in pressure.missing
        assert "SPX" not in pressure.missing

    def test_the_score_is_clamped_to_the_gauge(self) -> None:
        window = overnight_window(ist(2026, 9, 24, 8))
        crash = gap_pressure(
            window, quotes(SPX="-12", NASDAQ="-14", DJIA="-11", DAX="-9"), ist(2026, 9, 24, 8)
        )

        assert crash.score == Decimal("-100.00")
        assert crash.band is PressureBand.STRONG_DOWN

    def test_an_ordinary_bad_night_does_not_peg_the_gauge(self) -> None:
        """A composite that saturates on a normal session cannot tell a bad
        night from a crisis, which is the distinction it exists to draw."""
        window = overnight_window(ist(2026, 9, 24, 8))
        ordinary = gap_pressure(
            window, quotes(SPX="-1.0", NASDAQ="-1.1", DJIA="-0.8", DAX="-0.4"), ist(2026, 9, 24, 8)
        )

        assert Decimal("-100") < ordinary.score < Decimal("-10")

    def test_the_largest_mover_leads_the_waterfall(self) -> None:
        window = overnight_window(ist(2026, 9, 24, 8))
        pressure = gap_pressure(window, quotes(SHANGHAI="-0.2", SPX="-1.5"), ist(2026, 9, 24, 8))

        assert pressure.contributions[0].key == "SPX"


# -- implied open -------------------------------------------------------------


class TestImpliedOpen:
    #: Inside 09:15-15:30, so the cash market is trading.
    INTRADAY = ist(2026, 9, 24, 11)
    #: After the close: the session has settled and the next open gaps from it.
    OVERNIGHT = ist(2026, 9, 24, 22)

    def test_a_premium_to_spot_implies_a_gap_up(self) -> None:
        gift = quote("GIFTNIFTY", "0.5", price="23600")
        nifty = quote("NIFTY", "0.1", price="23450")

        implied = implied_open(gift, nifty, self.INTRADAY)

        assert implied is not None
        assert implied.gap_points == Decimal("150.00")
        assert implied.signal is GapSignal.GAP_UP

    def test_a_discount_implies_a_gap_down(self) -> None:
        implied = implied_open(
            quote("GIFTNIFTY", "-0.5", price="23300"),
            quote("NIFTY", "0", price="23450"),
            self.INTRADAY,
        )

        assert implied is not None
        assert implied.gap_points == Decimal("-150.00")
        assert implied.signal is GapSignal.GAP_DOWN

    def test_a_move_inside_the_dead_zone_reads_flat(self) -> None:
        """The same 0.15% dead-zone as the dashboard's gap card, so GAP UP /
        GAP DOWN / FLAT means one thing across the product."""
        implied = implied_open(
            quote("GIFTNIFTY", "0", price="23470"),
            quote("NIFTY", "0", price="23450"),
            self.INTRADAY,
        )

        assert implied is not None
        assert abs(implied.gap_percent) < Decimal("0.15")
        assert implied.signal is GapSignal.FLAT

    def test_while_nifty_trades_the_gap_is_from_the_previous_close(self) -> None:
        """Intraday, NIFTY spot and NIFTY's previous close are different
        numbers. The *gap* is where GIFT opens relative to the last
        settlement; the *basis* is its premium to where the index is trading
        right now. Using spot for both reports a gap measured from a level the
        market has already moved away from."""
        gift = quote("GIFTNIFTY", "0", price="23267.50")
        nifty = quote("NIFTY", "0.57", price="23446.80", previous_close="23315.50")

        implied = implied_open(gift, nifty, self.INTRADAY)

        assert implied is not None
        assert implied.nifty_is_trading is True
        # Gap: against the previous close, 23,315.50.
        assert implied.reference_close == Decimal("23315.50")
        assert implied.gap_points == Decimal("-48.00")
        # Basis: against spot, 23,446.80 - a different, larger discount.
        assert implied.basis == Decimal("-179.30")
        assert implied.signal is GapSignal.GAP_DOWN

    def test_once_nifty_has_closed_the_gap_is_from_that_close(self) -> None:
        """The overnight bug, with the numbers that exposed it.

        At 22:00 the cash market has settled at 23,140.50 and GIFT is trading
        23,103.50 - below the close the next session will open from. Measuring
        from the provider's ``previous_close`` instead reaches back to
        *yesterday's* 23,063.10 and prints GAP UP over a contract quoting a
        gap down: not merely imprecise, the opposite sign.
        """
        gift = quote("GIFTNIFTY", "-0.37", price="23103.50", previous_close="23188.50")
        nifty = quote("NIFTY", "0.34", price="23140.50", previous_close="23063.10")

        implied = implied_open(gift, nifty, self.OVERNIGHT)

        assert implied is not None
        assert implied.nifty_is_trading is False
        assert implied.reference_close == Decimal("23140.50")
        assert implied.gap_points == Decimal("-37.00")
        assert implied.gap_percent == Decimal("-0.16")
        assert implied.signal is GapSignal.GAP_DOWN

    def test_the_contract_carries_its_own_session_move(self) -> None:
        """GIFT's change against its own previous settlement, which is what
        every broker screen prints beside it. A card showing only the gap
        against NIFTY cannot be reconciled with one of those screens."""
        gift = quote("GIFTNIFTY", "-0.37", price="23103.50", previous_close="23188.50")
        nifty = quote("NIFTY", "0.34", price="23140.50", previous_close="23063.10")

        implied = implied_open(gift, nifty, self.OVERNIGHT)

        assert implied is not None
        assert implied.gift_change_percent == Decimal("-0.37")

    def test_before_the_open_the_last_close_is_already_the_base(self) -> None:
        """08:00: nothing has traded today, so the quote's own price is
        yesterday's close - which is exactly the level this morning's open
        gaps from."""
        implied = implied_open(
            quote("GIFTNIFTY", "0", price="23600"),
            quote("NIFTY", "0.1", price="23450", previous_close="23400"),
            ist(2026, 9, 24, 8),
        )

        assert implied is not None
        assert implied.reference_close == Decimal("23450")
        assert implied.gap_points == Decimal("150.00")

    def test_spot_stands_in_when_no_previous_close_was_published(self) -> None:
        gift = quote("GIFTNIFTY", "0", price="23600")
        nifty = GlobalQuote(
            key="NIFTY",
            price=Decimal("23450"),
            change=None,
            change_percent=None,
            previous_close=None,
        )

        implied = implied_open(gift, nifty, ist(2026, 9, 24, 11))

        assert implied is not None
        assert implied.gap_points == Decimal("150.00")

    def test_there_is_no_reading_without_both_legs(self) -> None:
        nifty = quote("NIFTY", "0", price="23450")
        now = ist(2026, 9, 24, 8)

        assert implied_open(None, nifty, now) is None
        assert implied_open(quote("GIFTNIFTY", "0", price="23600"), None, now) is None

    @pytest.mark.parametrize(
        ("percent", "expected"),
        [
            ("0.14", GapSignal.FLAT),
            ("-0.14", GapSignal.FLAT),
            ("0.15", GapSignal.GAP_UP),
            ("-0.15", GapSignal.GAP_DOWN),
        ],
    )
    def test_the_threshold_itself_is_a_gap(self, percent: str, expected: GapSignal) -> None:
        assert gap_signal(Decimal(percent)) is expected


class TestNiftyIsTrading:
    """Market hours alone are not enough - see the function's docstring."""

    def test_inside_the_session_on_a_day_that_printed(self) -> None:
        nifty = quote("NIFTY", "0", session=ist(2026, 9, 24, 11))

        assert nifty_is_trading(nifty, ist(2026, 9, 24, 11)) is True

    def test_after_the_close(self) -> None:
        nifty = quote("NIFTY", "0", session=ist(2026, 9, 24, 15, 30))

        assert nifty_is_trading(nifty, ist(2026, 9, 24, 22)) is False

    def test_the_clock_says_session_but_the_last_print_is_days_old(self) -> None:
        """A Saturday, or a holiday: 11:00 falls inside 09:15-15:30 and
        nothing is trading. Treating it as live would measure the gap from a
        close a whole session too far back."""
        stale = quote("NIFTY", "0", session=ist(2026, 9, 25, 15, 30))

        assert nifty_is_trading(stale, ist(2026, 9, 26, 11)) is False

    def test_no_print_timestamp_falls_back_to_the_hours(self) -> None:
        assert nifty_is_trading(quote("NIFTY", "0"), ist(2026, 9, 24, 11)) is True
        assert nifty_is_trading(quote("NIFTY", "0"), ist(2026, 9, 24, 22)) is False


# -- agreement ----------------------------------------------------------------


class TestAgreement:
    def test_the_two_reads_disagreeing_is_itself_the_signal(self) -> None:
        """A page that averaged the composite and GIFT into one arrow would
        erase the most useful state it can show."""
        window = overnight_window(ist(2026, 9, 24, 8))
        bearish = gap_pressure(window, quotes(SPX="-1.5", NASDAQ="-1.8"), ist(2026, 9, 24, 8))
        gift_up = implied_open(
            quote("GIFTNIFTY", "0", price="23600"),
            quote("NIFTY", "0", price="23450"),
            ist(2026, 9, 24, 8),
        )

        assert agreement(bearish, gift_up) is Agreement.DISAGREE

    def test_both_pointing_the_same_way_agrees(self) -> None:
        window = overnight_window(ist(2026, 9, 24, 8))
        bearish = gap_pressure(window, quotes(SPX="-1.5", NASDAQ="-1.8"), ist(2026, 9, 24, 8))
        gift_down = implied_open(
            quote("GIFTNIFTY", "0", price="23300"),
            quote("NIFTY", "0", price="23450"),
            ist(2026, 9, 24, 8),
        )

        assert agreement(bearish, gift_down) is Agreement.AGREE

    def test_a_flat_read_claims_neither(self) -> None:
        window = overnight_window(ist(2026, 9, 24, 8))
        flat = gap_pressure(window, quotes(SPX="0.01"), ist(2026, 9, 24, 8))
        gift_down = implied_open(
            quote("GIFTNIFTY", "0", price="23300"),
            quote("NIFTY", "0", price="23450"),
            ist(2026, 9, 24, 8),
        )

        assert agreement(flat, gift_down) is Agreement.UNKNOWN

    def test_no_gift_reading_is_unknown_not_agreement(self) -> None:
        window = overnight_window(ist(2026, 9, 24, 8))
        bearish = gap_pressure(window, quotes(SPX="-1.5"), ist(2026, 9, 24, 8))

        assert agreement(bearish, None) is Agreement.UNKNOWN


# -- region rollup ------------------------------------------------------------


class TestRegionRollup:
    def test_a_vix_spike_does_not_turn_a_falling_america_green(self) -> None:
        """The bug this pins was live on the page.

        VIX rose 6.8% on a night the S&P, NASDAQ and Dow all fell. Averaging it
        in with them printed "Americas +1.07%" - the exact opposite of what
        New York did.
        """
        rollups = region_rollup(
            MARKETS,
            quotes(SPX="-0.755", NASDAQ="-1.131", DJIA="-0.679", VIX="6.826"),
            {"americas": "Americas"},
        )
        americas = next(row for row in rollups if row.region == "americas")

        assert americas.change_percent is not None
        assert americas.change_percent < 0
        assert americas.members == 3

    def test_macro_rows_are_not_averaged_into_a_region(self) -> None:
        """Crude, gold, a currency and a bond yield share no unit and no
        direction; their mean is arithmetic on nonsense."""
        rollups = region_rollup(
            MARKETS, quotes(CRUDE="-0.9", GOLD="0.17", USDINR="0.0", US10Y="2.9"), {}
        )

        assert all(row.region != "macro" for row in rollups)
