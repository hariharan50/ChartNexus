"""Catalog domain rules and the refresh use case."""

from __future__ import annotations

from decimal import Decimal

import pytest

from chartnexus.contexts.instrument_catalog.application.ports import CatalogSyncResult
from chartnexus.contexts.instrument_catalog.application.use_cases import (
    GetInstrument,
    ListInstruments,
    ListInstrumentsQuery,
    SyncInstrumentCatalog,
)
from chartnexus.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)
from chartnexus.shared_kernel.domain.errors import NotFoundError, ValidationError

pytestmark = pytest.mark.unit


def make(symbol: str = "RELIANCE", **overrides: object) -> Instrument:
    fields: dict[str, object] = {
        "symbol": symbol,
        "kind": InstrumentKind.STOCK,
        "name": "RELIANCE INDUSTRIES LTD",
        "exchange": "NSE",
        "lot_size": 500,
        "tick_size": Decimal("0.1"),
        "spot_symbol": f"NSE:{symbol}-EQ",
        "futures_root": symbol,
    }
    fields.update(overrides)
    return Instrument(**fields)  # type: ignore[arg-type]


class FakeRepository:
    def __init__(self, instruments: list[Instrument] | None = None) -> None:
        self.instruments = {i.symbol: i for i in (instruments or [])}
        self.replaced: list[Instrument] | None = None

    async def get(self, symbol: str) -> Instrument | None:
        return self.instruments.get(symbol)

    async def search(self, **_: object) -> list[Instrument]:
        return list(self.instruments.values())

    async def symbols(self, *, active_only: bool = True) -> frozenset[str]:
        return frozenset(self.instruments)

    async def replace_all(self, instruments: list[Instrument]) -> CatalogSyncResult:
        self.replaced = instruments
        return CatalogSyncResult(added=len(instruments), updated=0, deactivated=0)


class FakeMaster:
    def __init__(self, instruments: list[Instrument]) -> None:
        self._instruments = instruments

    async def fetch(self) -> list[Instrument]:
        return self._instruments


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:  # pragma: no cover - not exercised here
        pass


# -- domain -----------------------------------------------------------------


def test_symbol_must_be_upper_case() -> None:
    with pytest.raises(ValidationError):
        make("reliance")


def test_symbol_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        make("  ")


def test_lot_size_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        make(lot_size=0)


def test_strike_step_may_be_absent_but_not_zero() -> None:
    assert make(strike_step=None).strike_step is None
    with pytest.raises(ValidationError):
        make(strike_step=Decimal("0"))


def test_ampersand_symbols_are_valid() -> None:
    """``M&M`` and ``GVT&D`` are real NSE tickers."""
    assert make("M&M").symbol == "M&M"


# -- use cases --------------------------------------------------------------


async def test_sync_replaces_the_universe_and_commits() -> None:
    repository = FakeRepository()
    uow = FakeUnitOfWork()
    incoming = [make("RELIANCE"), make("TCS")]

    result = await SyncInstrumentCatalog(
        repository=repository, master=FakeMaster(incoming), uow=uow
    )()

    assert repository.replaced == incoming
    assert result.added == 2
    assert uow.committed


async def test_sync_refuses_an_empty_master() -> None:
    """A master that downloaded as zero rows means the feed broke.

    Deactivating the whole universe on that basis would take the application
    offline, so the sync fails loudly and yesterday's catalog stands.
    """
    repository = FakeRepository([make("RELIANCE")])
    uow = FakeUnitOfWork()

    with pytest.raises(ValueError, match="refusing to empty the catalog"):
        await SyncInstrumentCatalog(repository=repository, master=FakeMaster([]), uow=uow)()

    assert repository.replaced is None
    assert not uow.committed


async def test_get_instrument_is_case_insensitive() -> None:
    repository = FakeRepository([make("RELIANCE")])

    assert (await GetInstrument(repository=repository)("reliance")).symbol == "RELIANCE"


async def test_get_instrument_raises_for_an_unknown_symbol() -> None:
    with pytest.raises(NotFoundError):
        await GetInstrument(repository=FakeRepository())("NOPE")


async def test_list_is_bounded_even_when_a_caller_asks_for_more() -> None:
    repository = FakeRepository([make("RELIANCE")])
    captured: dict[str, object] = {}

    async def search(**kwargs: object) -> list[Instrument]:
        captured.update(kwargs)
        return []

    repository.search = search  # type: ignore[method-assign]
    await ListInstruments(repository=repository)(ListInstrumentsQuery(limit=10_000))

    assert captured["limit"] == 500
