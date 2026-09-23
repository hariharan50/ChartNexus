"""Drawing the board for a series other than the near month.

Two things have to hold, and neither is obvious from the happy path: the
request has to reach the provider (a dropped ``series`` silently returns the
front month under a back month's label), and a series the open-interest sweep
does not cover has to be *reported* as unswept rather than rendered as a
market in which nothing is building up.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from marketcompass.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    DataSource,
    FuturesQuote,
    Provenance,
)
from marketcompass.infrastructure.brokers.futures_contract import contract_for
from marketcompass.infrastructure.brokers.mock.provider import MockMarketDataProvider
from marketcompass.infrastructure.catalog import registry
from marketcompass.infrastructure.futures.board_source import CatalogFuturesBoardSource
from marketcompass.infrastructure.futures.oi_cache import CachedOpenInterest
from marketcompass.infrastructure.time.clock import FixedClock
from marketcompass.shared_kernel.types.identifiers import TenantId, new_id

pytestmark = pytest.mark.unit

TENANT = TenantId(new_id())
NOW = datetime(2026, 9, 23, 6, 30, tzinfo=UTC)  # midday IST, inside the session
NSE_SERIES = (date(2026, 9, 29), date(2026, 10, 27), date(2026, 11, 23))
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
        reference_price=Decimal(1000),
    )


class RecordingProvider:
    """Prices whatever series it is asked for, and remembers which."""

    def __init__(self) -> None:
        self.series: int | None = None

    @property
    def name(self) -> str:
        return "fyers"

    async def get_futures_board(
        self, instruments: Any, *, series: int = 0
    ) -> dict[InstrumentSymbol, FuturesQuote]:
        self.series = series
        return {
            symbol: FuturesQuote(
                instrument=symbol,
                contract=f"NSE:{symbol.value}26FUT",
                expiry=contract_for(symbol, NOW.date(), series).isoformat(),
                price=Decimal(110),
                change=Decimal(10),
                change_percent=Decimal(10),
                volume=1000,
                day_high=Decimal(112),
                day_low=Decimal(108),
                open_interest=None,
                previous_open_interest=None,
                previous_close=Decimal(100),
                provenance=Provenance(source=DataSource.LIVE, fetched_at=NOW),
            )
            for symbol in instruments
        }


class Resolver:
    def __init__(self, provider: object) -> None:
        self._provider = provider

    async def resolve(self, tenant_id: TenantId) -> Any:
        return self._provider


class NearMonthOnlyCache:
    """A sweep configured to cover the near month and nothing further."""

    async def read_all(self, series: int = 0) -> dict[str, CachedOpenInterest]:
        if series != 0:
            return {}
        return {
            "RELIANCE": CachedOpenInterest(
                open_interest=1_200, previous_open_interest=1_000, observed_at=NOW
            )
        }


def build(provider: object, cache: object | None = None) -> CatalogFuturesBoardSource:
    return CatalogFuturesBoardSource(
        Resolver(provider),  # type: ignore[arg-type]
        MockMarketDataProvider(FixedClock(NOW)),
        oi_cache=cache,  # type: ignore[arg-type]
    )


# -- the request reaches the provider -------------------------------------------


@pytest.mark.asyncio
async def test_the_requested_series_is_what_gets_priced() -> None:
    provider = RecordingProvider()
    with registry.installed([instrument("RELIANCE")]):
        snapshot = await build(provider).read(TENANT, series=1)

    assert provider.series == 1
    assert snapshot.series == 1
    # The label is the date that series settles on, not the near month's.
    assert snapshot.expiry == "2026-10-27"


@pytest.mark.asyncio
async def test_a_series_past_what_the_exchange_lists_is_clamped() -> None:
    provider = RecordingProvider()
    with registry.installed([instrument("RELIANCE")]):
        snapshot = await build(provider).read(TENANT, series=99)
    assert snapshot.series <= 2


# -- open interest ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_swept_series_carries_open_interest() -> None:
    provider = RecordingProvider()
    with registry.installed([instrument("RELIANCE")]):
        snapshot = await build(provider, NearMonthOnlyCache()).read(TENANT, series=0)

    assert snapshot.has_open_interest is True
    assert snapshot.readings[0].open_interest == 1_200


@pytest.mark.asyncio
async def test_an_unswept_series_says_so_instead_of_reading_as_a_flat_market() -> None:
    """Four empty build-up panels are a claim, and it has to be the right one.

    Without this flag the page cannot tell "nobody is building a position" from
    "nobody measured", and the two look identical on screen.
    """
    provider = RecordingProvider()
    with registry.installed([instrument("RELIANCE")]):
        snapshot = await build(provider, NearMonthOnlyCache()).read(TENANT, series=2)

    assert snapshot.has_open_interest is False
    assert snapshot.readings[0].open_interest is None


# -- the picker --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_picker_offers_every_listed_series_with_a_representative_date() -> None:
    provider = RecordingProvider()
    rows = [
        instrument("RELIANCE"),
        instrument("TCS"),
        instrument("SENSEX", exchange="BSE", expiries=BSE_SERIES),
    ]
    with registry.installed(rows):
        options = await build(provider, NearMonthOnlyCache()).expiries(TENANT)

    assert [option.series for option in options] == [0, 1, 2]
    # Two NSE names against one BSE name, so the NSE date is the modal one —
    # a representative label, which is why every row still carries its own.
    assert [option.expiry for option in options] == [
        "2026-09-29",
        "2026-10-27",
        "2026-11-23",
    ]
    # The listing says nothing about open interest on purpose: whether a series
    # carries it depends on the provider that answers the board request, and a
    # second answer here could contradict the rows on screen.
    assert not hasattr(options[0], "has_open_interest")


# -- the generator -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_generator_gives_each_series_its_own_board() -> None:
    """Three identical boards under three dates would read as a broken picker.

    Back months genuinely trade at a wider premium to spot on a far thinner
    book, and the mock has to show that or the expiry control looks inert in
    development — which is where this application is actually used.
    """
    provider = MockMarketDataProvider(FixedClock(NOW))
    symbols = [InstrumentSymbol("RELIANCE")]
    with registry.installed([instrument("RELIANCE")]):
        near = await provider.get_futures_board(symbols, series=0)
        far = await provider.get_futures_board(symbols, series=2)

    near_quote = near[symbols[0]]
    far_quote = far[symbols[0]]
    assert far_quote.expiry != near_quote.expiry
    assert far_quote.price > near_quote.price  # carry compounds with time
    assert far_quote.open_interest is not None and near_quote.open_interest is not None
    assert far_quote.open_interest < near_quote.open_interest
    assert far_quote.volume < near_quote.volume
