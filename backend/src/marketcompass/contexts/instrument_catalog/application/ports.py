"""Ports the instrument-catalog use cases depend on."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from marketcompass.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)


@dataclass(frozen=True, slots=True)
class CatalogSyncResult:
    """What a sync actually changed — reported so a silent no-op is visible."""

    added: int
    updated: int
    deactivated: int

    @property
    def total(self) -> int:
        return self.added + self.updated


@runtime_checkable
class InstrumentRepository(Protocol):
    async def get(self, symbol: str) -> Instrument | None:
        """One instrument by canonical symbol, or ``None`` if unknown."""
        ...

    async def search(
        self,
        *,
        kind: InstrumentKind | None = None,
        search: str | None = None,
        active_only: bool = True,
        limit: int | None = None,
    ) -> list[Instrument]:
        """Catalog rows, filtered. Indices first, then alphabetically — the
        order a picker should show them in."""
        ...

    async def symbols(self, *, active_only: bool = True) -> frozenset[str]:
        """Just the symbol set. This is what instrument validation reads, so it
        is a distinct call from :meth:`search`: the caller wants membership, not
        rows, and should not pay for the rest of the columns."""
        ...

    async def replace_all(self, instruments: list[Instrument]) -> CatalogSyncResult:
        """Upsert every supplied instrument and deactivate the rest.

        Deactivate rather than delete: a symbol dropped from the F&O list still
        appears in yesterday's snapshots, and history pointing at a row that
        vanished is worse than a row flagged inactive.
        """
        ...


@runtime_checkable
class SymbolMasterPort(Protocol):
    async def fetch(self) -> list[Instrument]:
        """The current universe, as published by the exchange symbol master."""
        ...


@runtime_checkable
class UnitOfWork(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
