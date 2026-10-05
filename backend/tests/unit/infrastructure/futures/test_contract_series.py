"""Which contract a series index names, and what the board does with it.

The Future Lab can be pointed at the near, next or far month. A *series index*
rather than a date is the whole design, and these pin down why: the dates do
not agree across the universe, so one date could never name the same contract
for every row on a board.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from chartnexus.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)
from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.infrastructure.brokers.futures_contract import (
    MAX_SERIES,
    contract_for,
    expiries_for,
    to_futures_symbol,
)
from chartnexus.infrastructure.catalog import registry

pytestmark = pytest.mark.unit

TODAY = date(2026, 9, 23)

#: As NSE lists them in September 2026 — note the near month is a Tuesday, not
#: the last Thursday: the calendar heuristic this replaced gets it wrong.
NSE_SERIES = (date(2026, 9, 29), date(2026, 10, 27), date(2026, 11, 23))
#: BSE settles a day earlier, which is the reason none of this is keyed on a
#: single universe-wide date.
BSE_SERIES = (date(2026, 9, 28), date(2026, 10, 26), date(2026, 11, 24))


def instrument(
    symbol: str,
    *,
    exchange: str = "NSE",
    expiries: tuple[date, ...] = NSE_SERIES,
) -> Instrument:
    return Instrument(
        symbol=symbol,
        kind=InstrumentKind.STOCK,
        name=symbol.title(),
        exchange=exchange,
        lot_size=100,
        tick_size=Decimal("0.05"),
        spot_symbol=f"{exchange}:{symbol}-EQ",
        futures_root=symbol,
        front_expiry=expiries[0] if expiries else None,
        futures_expiries=expiries,
    )


# -- resolving a series ---------------------------------------------------------


def test_each_series_resolves_to_the_date_the_exchange_listed() -> None:
    with registry.installed([instrument("RELIANCE")]):
        symbol = InstrumentSymbol("RELIANCE")
        assert contract_for(symbol, TODAY, 0) == NSE_SERIES[0]
        assert contract_for(symbol, TODAY, 1) == NSE_SERIES[1]
        assert contract_for(symbol, TODAY, 2) == NSE_SERIES[2]


def test_two_instruments_can_disagree_about_the_same_series() -> None:
    """Which is exactly why the request carries an index and not a date."""
    with registry.installed(
        [instrument("RELIANCE"), instrument("SENSEX", exchange="BSE", expiries=BSE_SERIES)]
    ):
        assert contract_for(InstrumentSymbol("RELIANCE"), TODAY, 1) == date(2026, 10, 27)
        assert contract_for(InstrumentSymbol("SENSEX"), TODAY, 1) == date(2026, 10, 26)


def test_an_expired_series_is_dropped_rather_than_counted() -> None:
    """Series 0 has to mean "the contract trading now" on every day of the year.

    A list still holding last month's expiry would shift every index behind it,
    so a page showing the near month would quietly be drawing the next one.
    """
    stale = (date(2026, 8, 25), *NSE_SERIES)
    with registry.installed([instrument("RELIANCE", expiries=stale)]):
        listed = expiries_for(InstrumentSymbol("RELIANCE"), TODAY)
        assert listed == NSE_SERIES
        assert contract_for(InstrumentSymbol("RELIANCE"), TODAY, 0) == NSE_SERIES[0]


def test_a_series_the_instrument_does_not_list_clamps_to_its_furthest() -> None:
    """What the exchange would tell you, rather than an error page."""
    with registry.installed([instrument("RELIANCE", expiries=NSE_SERIES[:2])]):
        assert contract_for(InstrumentSymbol("RELIANCE"), TODAY, 2) == NSE_SERIES[1]


def test_an_uncatalogued_expiry_list_falls_back_to_the_calendar() -> None:
    """Wrong about the day, right about the month — and only the month is used.

    A symbol listed between catalog syncs has no expiries stored. The fallback
    still has to produce three distinct months, or the picker would offer the
    same contract three times.
    """
    with registry.installed([instrument("NEWCO", expiries=())]):
        listed = expiries_for(InstrumentSymbol("NEWCO"), TODAY)
        assert len(listed) == MAX_SERIES
        assert [day.month for day in listed] == [9, 10, 11]


def test_only_the_month_reaches_the_broker_symbol() -> None:
    """A holiday-shifted day must never change which series is priced."""
    with registry.installed([instrument("RELIANCE")]):
        symbol = InstrumentSymbol("RELIANCE")
        assert to_futures_symbol(symbol, contract_for(symbol, TODAY, 0)) == "NSE:RELIANCE26SEPFUT"
        assert to_futures_symbol(symbol, contract_for(symbol, TODAY, 1)) == "NSE:RELIANCE26OCTFUT"
        assert to_futures_symbol(symbol, contract_for(symbol, TODAY, 2)) == "NSE:RELIANCE26NOVFUT"
