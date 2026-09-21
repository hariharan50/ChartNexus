"""Ports the futures-analytics use cases depend on."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from marketcompass.contexts.futures_analytics.domain.buildup import FuturesReading
from marketcompass.shared_kernel.types.identifiers import TenantId


@dataclass(frozen=True, slots=True)
class BoardSnapshot:
    """What one board read produced, and how much of the universe it covers.

    ``universe`` travels with the readings rather than being counted by the
    caller, so the API layer never has to reach into the instrument catalog to
    describe its own response — that would be a context boundary crossed for a
    number the source already knows.
    """

    readings: list[FuturesReading] = field(default_factory=list)
    universe: int = 0
    #: Where the numbers came from — "live" or "mock". Carried so the client can
    #: say so: a board drawn from generated data looks identical to a real one,
    #: and this field is the only thing that distinguishes them.
    source: str = "mock"
    #: ISO date of the front-month contract, shared by most of these readings.
    #: Most, not all: NSE and BSE settle on different days, so each reading
    #: carries its own and this is the one the bulk of them agree on.
    expiry: str | None = None


@runtime_checkable
class FuturesBoardSource(Protocol):
    async def read(self, tenant_id: TenantId) -> BoardSnapshot:
        """The whole F&O universe's front-month futures, in one pass.

        One call, not one per instrument: the implementation batches against
        the broker, and the daily request quota does not survive two hundred
        round trips per refresh.

        Contracts the source could not price are omitted rather than returned
        with zeros, so an empty-ish board is visibly incomplete instead of
        quietly wrong.
        """
        ...


@dataclass(frozen=True, slots=True)
class BoardFrame:
    """One contract, at one instant, as captured for the archive.

    ``open_interest`` is optional because price and open interest are fetched
    on different cadences — see the persistence model's docstring — so a frame
    may legitimately carry a price and no OI.
    """

    symbol: str
    session_date: date
    captured_at: datetime
    price: Decimal
    open_interest: int | None = None
    volume: int | None = None
    expiry: str | None = None
    #: "live" or "mock". A generated frame must never be stored as live: the
    #: archive outlives the process that wrote it, and a mislabelled row is a
    #: lie that cannot be detected later.
    source: str = "mock"


@runtime_checkable
class FuturesBoardHistoryWriter(Protocol):
    async def save_frames(self, frames: list[BoardFrame]) -> int:
        """Append one sweep's frames, ignoring any instant already stored.

        Returns how many were actually written. Idempotent on
        ``(symbol, captured_at)`` so a restarted worker re-running a sweep
        cannot double up the series.
        """
        ...


@runtime_checkable
class FuturesBoardHistoryReader(Protocol):
    async def frames_for(self, symbol: str, session_date: date) -> list[BoardFrame]:
        """Every stored frame for one contract on one trading day, oldest first."""
        ...
