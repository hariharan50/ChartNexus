"""The mock provider must serve any catalogued instrument, not just indices.

This is the point of the whole catalog change. Before it, the mock generator
held three hand-written dicts with no default, so a stock symbol raised
``KeyError`` — a 500 — rather than producing data. The universe is now 219
instruments spanning a fractional strike step and a four-figure price range,
and every one of them has to simulate.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from chartnexus.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)
from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import DataSource
from chartnexus.infrastructure.brokers.futures_contract import (
    front_month_for,
    local_front_month,
    to_futures_symbol,
)
from chartnexus.infrastructure.brokers.mock.option_chain_factory import build_option_chain
from chartnexus.infrastructure.brokers.mock.quote_factory import (
    build_quote,
    open_interest_at,
    previous_open_interest,
    previous_volume_at,
    volume_at,
)
from chartnexus.infrastructure.brokers.mock.session_model import (
    IST,
    base_level,
    lot_size,
    strike_step,
)
from chartnexus.infrastructure.catalog import registry
from chartnexus.shared_kernel.domain.errors import ValidationError
from tests.conftest import CATALOG_FIXTURE

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 6, 6, 30, tzinfo=UTC)


@pytest.mark.parametrize("symbol", [row.symbol for row in CATALOG_FIXTURE])
def test_every_catalogued_instrument_quotes(symbol: str) -> None:
    """Indices and stocks alike — including the one with an ampersand."""
    quote = build_quote(InstrumentSymbol(symbol), NOW)

    assert quote.price > 0
    # The one thing this provider must never do is look like a real feed.
    assert quote.provenance.source is DataSource.MOCK


@pytest.mark.parametrize("symbol", [row.symbol for row in CATALOG_FIXTURE])
def test_a_quote_carries_an_opening_print_near_its_own_price(symbol: str) -> None:
    """The gap card renders the open beside the spot, so the two must agree.

    Both come off the one seeded walk, which caps a session's excursion. An
    open drawn from anywhere else would show as an implausible overnight jump.
    """
    quote = build_quote(InstrumentSymbol(symbol), NOW)

    assert quote.day_open is not None
    assert quote.previous_close is not None
    drift = abs(quote.day_open - quote.price) / quote.price
    assert drift < Decimal("0.05")


def test_the_overnight_gap_differs_from_one_session_to_the_next() -> None:
    """A previous close taken from the flat base level would be identical
    every day, leaving the indicator permanently stuck on one reading."""
    nifty = InstrumentSymbol("NIFTY")
    gaps = set()
    for day in (4, 5, 6):
        quote = build_quote(nifty, datetime(2026, 8, day, 6, 30, tzinfo=UTC))
        assert quote.day_open is not None
        assert quote.previous_close is not None
        gaps.add(quote.day_open - quote.previous_close)

    assert len(gaps) == 3


def test_a_monday_gap_is_measured_against_friday() -> None:
    """2026-08-10 is a Monday; its previous close is Friday the 7th's, not a
    weekend session that never traded."""
    nifty = InstrumentSymbol("NIFTY")
    monday = build_quote(nifty, datetime(2026, 8, 10, 6, 30, tzinfo=UTC))
    friday = build_quote(nifty, datetime(2026, 8, 7, 12, 0, tzinfo=UTC))

    assert monday.previous_close == friday.price


@pytest.mark.parametrize("symbol", [row.symbol for row in CATALOG_FIXTURE])
def test_every_catalogued_instrument_builds_a_chain(symbol: str) -> None:
    chain = build_option_chain(InstrumentSymbol(symbol), NOW, None)

    assert chain.strikes
    assert chain.lot_size == lot_size(InstrumentSymbol(symbol))


def test_a_stock_uses_its_own_geometry_not_an_index_scaled_guess() -> None:
    """The bug the old hand-written table caused, pinned as a test.

    RELIANCE trades near 1,270 on a 10-point ladder; NIFTY near 24,647 on a 50.
    Deriving one from the other is exactly what went wrong before.
    """
    reliance = InstrumentSymbol("RELIANCE")
    nifty = InstrumentSymbol("NIFTY")

    assert base_level(reliance) == Decimal("1270")
    assert strike_step(reliance) == Decimal("10")
    assert lot_size(reliance) == 500
    assert base_level(nifty) != base_level(reliance)


def test_a_fractional_strike_step_survives() -> None:
    """Nineteen real names trade on a 2.5 step; an int would silently truncate."""
    ashokley = InstrumentSymbol("ASHOKLEY")
    assert strike_step(ashokley) == Decimal("2.5")

    strikes = sorted({row.strike for row in build_option_chain(ashokley, NOW, None).strikes})
    gaps = {strikes[i + 1] - strikes[i] for i in range(len(strikes) - 1)}
    assert gaps == {Decimal("2.5")}


def test_futures_symbols_use_each_instrument_s_own_exchange_and_root() -> None:
    contract = local_front_month(NOW.date())

    # The index root differs from its canonical name, and SENSEX is on BSE.
    assert to_futures_symbol(InstrumentSymbol("NIFTY"), contract).startswith("NSE:NIFTY")
    assert to_futures_symbol(InstrumentSymbol("SENSEX"), contract).startswith("BSE:SENSEX")
    assert to_futures_symbol(InstrumentSymbol("RELIANCE"), contract).startswith("NSE:RELIANCE")


def test_an_uncatalogued_symbol_is_refused_rather_than_invented() -> None:
    """Fabricating numbers for an instrument that does not exist would be worse
    than failing, so this raises instead of falling back to a default."""
    with pytest.raises(ValidationError, match="not a tradeable instrument"):
        build_quote(InstrumentSymbol("DOGECOIN"), NOW)


# -- the session clock ------------------------------------------------------


@pytest.mark.parametrize(
    ("ist_hhmm", "expect_drift"),
    [
        ((6, 0), False),  # pre-open: nothing has traded
        ((9, 0), False),  # still pre-open
        ((9, 45), True),  # half an hour into the session
        ((13, 0), True),  # midday
        ((15, 30), True),  # near the close
        ((20, 0), True),  # after the close: the day's drift stands
    ],
)
def test_open_interest_drifts_on_exchange_local_time(
    ist_hhmm: tuple[int, int], expect_drift: bool
) -> None:
    """Regression: the session window is IST, the clock is UTC.

    Comparing the two directly shifted the drift window by five and a half
    hours, so open interest sat frozen at yesterday's close for the whole
    Indian trading day and every contract on the dashboard read as neutral.
    """
    hour, minute = ist_hhmm
    moment = datetime(2026, 9, 21, hour, minute, tzinfo=IST)
    instrument = InstrumentSymbol("RELIANCE")

    previous = previous_open_interest(instrument, moment.date())
    now = open_interest_at(instrument, moment)

    assert (now != previous) is expect_drift


def test_the_same_instant_gives_the_same_open_interest_in_any_timezone() -> None:
    """UTC and IST spellings of one moment are the same moment."""
    instrument = InstrumentSymbol("TCS")
    ist = datetime(2026, 9, 21, 13, 0, tzinfo=IST)

    assert open_interest_at(instrument, ist) == open_interest_at(instrument, ist.astimezone(UTC))


# -- volume -----------------------------------------------------------------


def test_volume_differs_between_instruments() -> None:
    """Regression: the formula had no instrument term, so all 210 contracts
    reported identical volume and the column was pure noise on the board."""
    midday = datetime(2026, 9, 21, 13, 0, tzinfo=IST)
    volumes = {
        symbol: volume_at(InstrumentSymbol(symbol), midday)
        for symbol in ("RELIANCE", "TCS", "ASHOKLEY", "M&M", "NIFTY")
    }

    assert len(set(volumes.values())) == len(volumes)


def test_volume_accumulates_through_the_session() -> None:
    instrument = InstrumentSymbol("RELIANCE")
    morning = volume_at(instrument, datetime(2026, 9, 21, 10, 0, tzinfo=IST))
    afternoon = volume_at(instrument, datetime(2026, 9, 21, 15, 0, tzinfo=IST))

    assert afternoon > morning


def test_day_over_day_volume_change_stays_plausible() -> None:
    """Deriving yesterday from an independent draw produced changes of
    +9,900%. A contract's liquidity is a property of the contract."""
    midday = datetime(2026, 9, 21, 13, 0, tzinfo=IST)

    for symbol in CATALOG_FIXTURE:
        instrument = InstrumentSymbol(symbol.symbol)
        now = volume_at(instrument, midday)
        before = previous_volume_at(instrument, midday)
        change = (now - before) / before * 100
        assert -60 < change < 130, f"{symbol.symbol} moved {change:.0f}%"


def test_before_the_open_the_previous_session_is_shown() -> None:
    """What a real terminal does: yesterday's completed figures stand until
    new ticks arrive, rather than a board of zeros."""
    instrument = InstrumentSymbol("RELIANCE")
    assert volume_at(instrument, datetime(2026, 9, 21, 7, 30, tzinfo=IST)) > 0


# -- contract resolution ----------------------------------------------------


def test_the_front_month_comes_from_the_catalog_not_the_calendar() -> None:
    """NSE settles September 2026 on Tuesday the 29th, not the last Thursday.

    The two disagree from the 25th to the 29th, and during that window the
    calendar guess rolls to October while September contracts are still
    trading — building symbols for a series nobody asked for.
    """
    listed = date(2026, 9, 29)
    rows = [
        Instrument(
            symbol="RELIANCE",
            kind=InstrumentKind.STOCK,
            name="RELIANCE",
            exchange="NSE",
            lot_size=500,
            tick_size=Decimal("0.05"),
            spot_symbol="NSE:RELIANCE-EQ",
            futures_root="RELIANCE",
            strike_step=Decimal(10),
            reference_price=Decimal(1270),
            front_expiry=listed,
        )
    ]

    with registry.installed(rows):
        resolved = front_month_for(InstrumentSymbol("RELIANCE"), date(2026, 9, 26))

    assert resolved == listed
    # The calendar would have rolled to October by the 26th.
    assert local_front_month(date(2026, 9, 26)).month == 10


def test_an_uncatalogued_expiry_falls_back_to_the_calendar() -> None:
    """A symbol listed between syncs still has to resolve to something."""
    resolved = front_month_for(InstrumentSymbol("NIFTY"), date(2026, 9, 1))

    assert resolved == local_front_month(date(2026, 9, 1))


def test_a_lapsed_catalog_expiry_is_not_used() -> None:
    """A stale sync must not pin the board to a contract that has expired."""
    rows = [
        Instrument(
            symbol="RELIANCE",
            kind=InstrumentKind.STOCK,
            name="RELIANCE",
            exchange="NSE",
            lot_size=500,
            tick_size=Decimal("0.05"),
            spot_symbol="NSE:RELIANCE-EQ",
            futures_root="RELIANCE",
            front_expiry=date(2026, 8, 25),
        )
    ]

    with registry.installed(rows):
        resolved = front_month_for(InstrumentSymbol("RELIANCE"), date(2026, 9, 26))

    assert resolved > date(2026, 9, 26)
