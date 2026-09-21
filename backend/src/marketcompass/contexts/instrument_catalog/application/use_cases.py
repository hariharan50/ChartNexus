"""Reading the catalog, and refreshing it from the exchange symbol master."""

from __future__ import annotations

from dataclasses import dataclass

from marketcompass.contexts.instrument_catalog.application.ports import (
    CatalogSyncResult,
    InstrumentRepository,
    SymbolMasterPort,
    UnitOfWork,
)
from marketcompass.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)
from marketcompass.shared_kernel.domain.errors import NotFoundError

# A picker asking for "everything" still gets a bounded response. The universe
# is ~220 rows today; this leaves headroom without letting a missing filter
# turn into an unbounded query.
DEFAULT_LIST_LIMIT = 500


@dataclass(frozen=True, slots=True)
class ListInstrumentsQuery:
    kind: InstrumentKind | None = None
    search: str | None = None
    limit: int = DEFAULT_LIST_LIMIT


@dataclass(slots=True)
class ListInstruments:
    repository: InstrumentRepository

    async def __call__(self, query: ListInstrumentsQuery) -> list[Instrument]:
        return await self.repository.search(
            kind=query.kind,
            search=query.search,
            active_only=True,
            limit=min(query.limit, DEFAULT_LIST_LIMIT),
        )


@dataclass(slots=True)
class GetInstrument:
    repository: InstrumentRepository

    async def __call__(self, symbol: str) -> Instrument:
        instrument = await self.repository.get(symbol.strip().upper())
        if instrument is None:
            raise NotFoundError("instrument", symbol)
        return instrument


@dataclass(slots=True)
class SyncInstrumentCatalog:
    """Refresh the catalog from the exchange symbol master.

    Safe to run repeatedly: the master is the source of truth, so the sync is a
    full replace rather than a diff the caller has to reason about. It refuses
    an empty fetch — a symbol master that downloaded as zero rows means the feed
    broke, and deactivating the entire universe on that basis would take the
    whole application offline.
    """

    repository: InstrumentRepository
    master: SymbolMasterPort
    uow: UnitOfWork

    async def __call__(self) -> CatalogSyncResult:
        instruments = await self.master.fetch()
        if not instruments:
            raise ValueError("symbol master returned no instruments; refusing to empty the catalog")

        result = await self.repository.replace_all(instruments)
        await self.uow.commit()
        return result
