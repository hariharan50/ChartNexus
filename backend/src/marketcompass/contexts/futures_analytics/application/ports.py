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
    #: ISO date of the contract series these readings are for, shared by most
    #: of them. Most, not all: NSE and BSE settle on different days, so each
    #: reading carries its own and this is the one the bulk of them agree on.
    expiry: str | None = None
    #: Which series was read — 0 near month, 1 next, 2 far. Echoed back so a
    #: response can never be mistaken for a different contract's.
    series: int = 0
    #: Whether open interest was available for this series. ``False`` leaves
    #: every row NEUTRAL, and the page has to say why rather than presenting an
    #: empty build-up board as a market with no build-ups in it.
    has_open_interest: bool = True


@dataclass(frozen=True, slots=True)
class ExpiryOption:
    """One contract series the board can be drawn for."""

    series: int
    #: The date most instruments in the universe settle this series on. A
    #: representative, not a universal truth — the rows themselves carry their
    #: own — and the label the picker shows.
    expiry: str

    # Deliberately no "has open interest" flag here. Whether a series carries
    # it depends on the provider that answers the request — the generator
    # supplies it with every quote, a live broker only where the sweep has
    # reached — so the listing cannot know, and a second answer that disagreed
    # with the board's own would be worse than no answer at all. The board
    # response carries the one that counts.


@runtime_checkable
class FuturesBoardSource(Protocol):
    async def read(self, tenant_id: TenantId, *, series: int = 0) -> BoardSnapshot:
        """The whole F&O universe's futures for one series, in one pass.

        One call, not one per instrument: the implementation batches against
        the broker, and the daily request quota does not survive two hundred
        round trips per refresh.

        ``series`` is an index into each instrument's own listed expiries — 0
        is the near month — rather than a date, because the dates do not agree
        across the universe and one of them could never name the same contract
        for every row.

        Contracts the source could not price are omitted rather than returned
        with zeros, so an empty-ish board is visibly incomplete instead of
        quietly wrong.
        """
        ...

    async def expiries(self, tenant_id: TenantId) -> list[ExpiryOption]:
        """The series a board can be drawn for, nearest first.

        Synchronous knowledge in an async signature: it reads the catalog, not
        the market. Declared on the port anyway so the API never has to reach
        into the instrument catalog itself — that would be a context boundary
        crossed for a list the source already assembles.
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
