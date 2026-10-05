"""Ports and DTOs the ingest use case depends on.

The context stays free of any import of ``market_data``, ``options_analytics``,
or the persistence layer: infrastructure adapters satisfy ``ChainSource`` (by
resolving the tenant's broker provider) and ``SnapshotWriter`` (by writing rows).
The DTOs below are the context's own shapes, not borrowed domain types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ChainRowToWrite:
    """One captured leg of one strike."""

    strike: Decimal
    option_type: str  # "CE" | "PE"
    oi: int
    oi_change: int
    volume: int
    ltp: Decimal | None = None
    iv: Decimal | None = None
    delta: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ChainObservation:
    """A live option chain as fetched, before header metrics are derived.

    ``source`` is the provider's provenance name — ``"live"`` from a broker,
    ``"mock"`` from the simulator. The use case decides whether a mock
    observation is worth persisting.
    """

    symbol: str
    captured_at: datetime
    spot: Decimal
    rows: tuple[ChainRowToWrite, ...]
    source: str
    expiry: str | None = None
    future_price: Decimal | None = None
    lot_size: int | None = None


@dataclass(frozen=True, slots=True)
class SnapshotToWrite:
    """The full row set persisted for one capture — header plus its legs."""

    symbol: str
    session_date: date
    captured_at: datetime
    spot: Decimal
    source: str
    rows: tuple[ChainRowToWrite, ...] = field(default_factory=tuple)
    expiry: str | None = None
    future_price: Decimal | None = None
    lot_size: int | None = None
    atm_strike: Decimal | None = None
    total_call_oi: int | None = None
    total_put_oi: int | None = None
    pcr_oi: Decimal | None = None
    max_pain_strike: Decimal | None = None


@runtime_checkable
class ChainSource(Protocol):
    """Yields a live option chain for a symbol.

    Returns ``None`` when the symbol is not one the source can quote (so the
    caller skips it rather than treating it as a failure).
    """

    async def fetch(self, symbol: str, *, expiry: str | None = None) -> ChainObservation | None: ...

    async def expiries(self, symbol: str) -> tuple[str, ...]:
        """The expiries worth archiving for ``symbol``, nearest first.

        Empty when the source cannot say, which the caller reads as "just
        capture whatever the chain resolves to" - the behaviour before any of
        this existed.
        """
        ...


@runtime_checkable
class SnapshotWriter(Protocol):
    async def save(self, snapshot: SnapshotToWrite) -> None: ...

    async def latest_rows(
        self, symbol: str, session_date: date, expiry: str | None = None
    ) -> tuple[ChainRowToWrite, ...] | None:
        """The legs of the most recent capture, for duplicate detection.

        Scoped to ``expiry`` when one is given. Without that scope a tick that
        archives several contracts compares each against whichever of them was
        written last, so the frozen-tape check stops comparing like with like
        and silently stops working.

        ``None`` when nothing is stored for that symbol-day yet.
        """
        ...

    async def has_source(self, symbol: str, session_date: date, source: str) -> bool:
        """Whether any capture of that provenance exists for the symbol-day."""
        ...


@runtime_checkable
class SnapshotPruner(Protocol):
    """Deletes archived snapshots whose session predates ``cutoff``.

    Returns the number of *snapshots* removed; per-strike rows go with them by
    the database's cascade, which is why this is one call and not two.
    """

    async def delete_sessions_before(self, cutoff: date) -> int: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class MarketCalendar(Protocol):
    def is_open(self, moment: datetime) -> bool: ...
