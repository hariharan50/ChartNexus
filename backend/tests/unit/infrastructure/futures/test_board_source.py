"""How the board degrades when the broker has nothing to say.

The defect these pin down was real and user-visible: a tenant *with* a FYERS
connection got a completely empty Stocks page the moment their token lapsed or
the market was shut, while a tenant with no broker at all got a full one. The
board swallowed every batch failure and returned an empty result, which the UI
then rendered as "No stocks priced." with no explanation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from chartnexus.contexts.futures_analytics.domain.buildup import BuildupState, classify
from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import (
    DataSource,
    FuturesQuote,
    Provenance,
)
from chartnexus.infrastructure.futures.board_source import CatalogFuturesBoardSource
from chartnexus.infrastructure.futures.oi_cache import CachedOpenInterest
from chartnexus.shared_kernel.types.identifiers import TenantId, new_id

pytestmark = pytest.mark.unit

TENANT = TenantId(new_id())
NOW = datetime(2026, 9, 21, 7, 30, tzinfo=UTC)


def quote(symbol: str, *, oi: int | None = 1100) -> FuturesQuote:
    return FuturesQuote(
        instrument=InstrumentSymbol(symbol),
        contract=f"NSE:{symbol}26SEPFUT",
        expiry="2026-09-29",
        price=Decimal(110),
        change=Decimal(10),
        change_percent=Decimal(10),
        volume=1000,
        day_high=Decimal(112),
        day_low=Decimal(108),
        open_interest=oi,
        previous_open_interest=1000,
        previous_close=Decimal(100),
        provenance=Provenance(source=DataSource.MOCK, fetched_at=NOW),
    )


class StubProvider:
    """A provider that returns whatever it was told to."""

    def __init__(
        self,
        board: dict[str, FuturesQuote] | None = None,
        *,
        fails: bool = False,
        name: str = "fyers",
    ):
        self._board = board or {}
        self._fails = fails
        self._name = name
        self.calls = 0
        #: Which series the board asked this provider for.
        self.series = 0

    @property
    def name(self) -> str:
        """Provenance is decided by this, so a stub standing in for the mock
        has to say so."""
        return self._name

    async def get_futures_board(self, instruments, *, series=0):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.series = series
        if self._fails:
            raise RuntimeError("broker is down")
        return {InstrumentSymbol(s): q for s, q in self._board.items()}


class Resolver:
    def __init__(self, provider: object | None) -> None:
        self._provider = provider

    async def resolve(self, tenant_id: TenantId):  # type: ignore[no-untyped-def]
        if self._provider is None:
            raise RuntimeError("no broker connection")
        return self._provider


def mock_provider() -> StubProvider:
    return StubProvider({"RELIANCE": quote("RELIANCE"), "TCS": quote("TCS")}, name="mock")


async def test_a_live_board_is_used_and_labelled_live() -> None:
    live = StubProvider({"RELIANCE": quote("RELIANCE")})
    fallback = mock_provider()

    snapshot = await CatalogFuturesBoardSource(Resolver(live), fallback).read(TENANT)

    assert [r.symbol for r in snapshot.readings] == ["RELIANCE"]
    assert snapshot.source == "live"
    assert fallback.calls == 0


async def test_an_empty_live_board_degrades_to_the_mock() -> None:
    """The bug: a connected broker that returns nothing left the page blank."""
    live = StubProvider({})
    fallback = mock_provider()

    snapshot = await CatalogFuturesBoardSource(Resolver(live), fallback).read(TENANT)

    assert len(snapshot.readings) == 2
    assert snapshot.source == "mock"
    assert fallback.calls == 1


async def test_a_raising_broker_degrades_rather_than_propagating() -> None:
    live = StubProvider(fails=True)
    fallback = mock_provider()

    snapshot = await CatalogFuturesBoardSource(Resolver(live), fallback).read(TENANT)

    assert len(snapshot.readings) == 2
    assert snapshot.source == "mock"


async def test_a_tenant_with_no_broker_uses_the_mock_and_says_so() -> None:
    fallback = mock_provider()

    snapshot = await CatalogFuturesBoardSource(Resolver(None), fallback).read(TENANT)

    assert len(snapshot.readings) == 2
    assert snapshot.source == "mock"


async def test_a_quote_without_open_interest_keeps_its_price() -> None:
    """The defect this replaces: FYERS' quote endpoint carries no open
    interest, so requiring it discarded every row and swapped an entire live
    board for simulated data. A missing column must not cost a real price."""
    live = StubProvider({"RELIANCE": quote("RELIANCE", oi=None)})

    snapshot = await CatalogFuturesBoardSource(Resolver(live), mock_provider()).read(TENANT)

    assert snapshot.source == "live"
    assert [r.symbol for r in snapshot.readings] == ["RELIANCE"]


async def test_a_row_without_open_interest_is_not_classified() -> None:
    """Price alone cannot separate fresh longs from short covering, so the
    honest answer is NEUTRAL — never a guess."""
    live = StubProvider({"RELIANCE": quote("RELIANCE", oi=None)})

    snapshot = await CatalogFuturesBoardSource(Resolver(live), mock_provider()).read(TENANT)
    reading = snapshot.readings[0]

    assert reading.oi_change_percent is None
    assert classify(reading) is BuildupState.NEUTRAL


async def test_the_universe_is_the_catalog_not_what_was_priced() -> None:
    live = StubProvider({"RELIANCE": quote("RELIANCE")})

    snapshot = await CatalogFuturesBoardSource(Resolver(live), mock_provider()).read(TENANT)

    # The suite-wide catalog fixture has six instruments; only one priced.
    assert snapshot.universe == 6
    assert len(snapshot.readings) == 1


async def test_readings_carry_enough_to_classify() -> None:
    live = StubProvider({"RELIANCE": quote("RELIANCE")})

    snapshot = await CatalogFuturesBoardSource(Resolver(live), mock_provider()).read(TENANT)
    reading = snapshot.readings[0]

    assert reading.kind == "stock"
    assert reading.lot_size == 500
    assert classify(reading) is BuildupState.LONG_BUILDUP


async def test_a_tenant_whose_broker_is_unusable_is_not_told_the_data_is_live() -> None:
    """The resolver builds its own mock when a connection cannot be used.

    Comparing against our fallback by object identity missed that one and
    stamped generated numbers "live", which is the single thing the provenance
    field exists to stop.
    """
    resolver_mock = StubProvider({"RELIANCE": quote("RELIANCE")}, name="mock")

    snapshot = await CatalogFuturesBoardSource(Resolver(resolver_mock), mock_provider()).read(
        TENANT
    )

    assert snapshot.readings  # data did arrive
    assert snapshot.source == "mock"  # but it is not real


# -- open interest from the sweep -------------------------------------------


class FakeOiCache:
    """Stands in for the Redis cache the background sweep fills."""

    def __init__(self, entries: dict[str, CachedOpenInterest] | None = None) -> None:
        self._entries = entries or {}

    async def read_all(self, series: int = 0) -> dict[str, CachedOpenInterest]:
        # Keyed by series like the real cache: a sweep that covers only the
        # near month leaves the others genuinely empty, which is what lets the
        # board report "not swept" rather than showing a stale figure.
        return self._entries if series == 0 else {}


def cached(oi: int, previous: int | None) -> CachedOpenInterest:
    return CachedOpenInterest(
        open_interest=oi,
        previous_open_interest=previous,
        observed_at=datetime(2026, 9, 21, 7, 0, tzinfo=UTC),
    )


async def test_open_interest_is_merged_from_the_sweep() -> None:
    """Price comes with the board; open interest comes from the background
    sweep, because the endpoint carrying it takes one contract per request."""
    live = StubProvider({"RELIANCE": quote("RELIANCE", oi=None)})
    cache = FakeOiCache({"RELIANCE": cached(2000, 1500)})

    snapshot = await CatalogFuturesBoardSource(
        Resolver(live),
        mock_provider(),
        oi_cache=cache,  # type: ignore[arg-type]
    ).read(TENANT)
    reading = snapshot.readings[0]

    assert reading.open_interest == 2000
    assert reading.open_interest_open == 1500
    assert classify(reading) is BuildupState.LONG_BUILDUP


async def test_a_contract_the_sweep_missed_keeps_its_price() -> None:
    live = StubProvider({"RELIANCE": quote("RELIANCE", oi=None)})

    snapshot = await CatalogFuturesBoardSource(
        Resolver(live),
        mock_provider(),
        oi_cache=FakeOiCache({}),  # type: ignore[arg-type]
    ).read(TENANT)
    reading = snapshot.readings[0]

    assert reading.price == Decimal(110)
    assert reading.open_interest is None
    assert classify(reading) is BuildupState.NEUTRAL


async def test_the_board_works_with_no_cache_at_all() -> None:
    """The cache is optional; without it the board loses a column, not a page."""
    live = StubProvider({"RELIANCE": quote("RELIANCE", oi=None)})

    snapshot = await CatalogFuturesBoardSource(Resolver(live), mock_provider()).read(TENANT)

    assert snapshot.readings
    assert snapshot.source == "live"


async def test_real_open_interest_is_never_merged_onto_a_simulated_board() -> None:
    """The sweep's figures are observed; a mock board's prices are not.

    Pairing them would classify a generated price move against a real
    open-interest move and present the result with the same confidence as a
    true one — two unrelated worlds in a single row.
    """
    cache = FakeOiCache({"RELIANCE": cached(9_999_999, 1)})

    snapshot = await CatalogFuturesBoardSource(
        Resolver(None),
        mock_provider(),
        oi_cache=cache,  # type: ignore[arg-type]
    ).read(TENANT)

    assert snapshot.source == "mock"
    assert all(r.open_interest != 9_999_999 for r in snapshot.readings)


async def test_a_board_that_degraded_does_not_keep_the_live_open_interest() -> None:
    """A broker that answered with nothing falls back to the mock, and the
    fallback must be internally consistent too."""
    live = StubProvider({})
    cache = FakeOiCache({"RELIANCE": cached(9_999_999, 1)})

    snapshot = await CatalogFuturesBoardSource(
        Resolver(live),
        mock_provider(),
        oi_cache=cache,  # type: ignore[arg-type]
    ).read(TENANT)

    assert snapshot.source == "mock"
    assert all(r.open_interest != 9_999_999 for r in snapshot.readings)
