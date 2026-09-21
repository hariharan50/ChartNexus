"""Ports the futures-analytics use cases depend on."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    #: ISO date of the front-month contract these readings are for. The board
    #: is front-month only, so one date describes every row.
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
