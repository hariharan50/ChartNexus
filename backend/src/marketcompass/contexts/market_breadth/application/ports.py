"""Ports the market-breadth use cases depend on.

Two sources, because the pages draw on two genuinely different kinds of data:
a priced index, which the broker can answer, and the exchange's daily
participant file, which it cannot.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from marketcompass.contexts.market_breadth.domain.breadth import SectorRow
from marketcompass.contexts.market_breadth.domain.breadth_series import PricePoint
from marketcompass.contexts.market_breadth.domain.constituents import IndexSnapshot
from marketcompass.contexts.market_breadth.domain.flows import FlowDay
from marketcompass.contexts.market_breadth.domain.open_interest import OiRow
from marketcompass.shared_kernel.types.identifiers import TenantId


@runtime_checkable
class IndexConstituentSource(Protocol):
    async def read(self, tenant_id: TenantId, index: str) -> IndexSnapshot:
        """Every member of ``index``, priced against its previous close.

        One call for the whole index, not one per member: a fifty-name index
        refreshed on a fifteen-second poll would exhaust the shared daily
        broker quota before lunch.

        Members the source could not price are returned with a ``None``
        previous close rather than omitted, so the page can show the index's
        real membership and say which rows are missing prints.
        """
        ...

    def universe(self) -> tuple[str, ...]:
        """Which indices this source can answer for, in display order.

        Synchronous because it reads a static membership table, not the
        market. The API layer uses it to validate the ``index`` query
        parameter instead of hardcoding a list of its own.
        """
        ...


@runtime_checkable
class BreadthHistorySource(Protocol):
    """The captured session, as breadth needs it.

    The futures board is already archived minute by minute for the whole F&O
    universe, which is the only reason an intraday breadth series exists at
    all — nothing writes breadth counts to a table. This port reads that
    archive without this context having to know it is the futures board's:
    ``market_breadth`` may not import ``futures_analytics``, and the adapter
    behind this translates.
    """

    async def prices(self, session: date, symbols: Sequence[str]) -> list[PricePoint]:
        """Every captured price for these symbols on one session, any order.

        One query for the whole scope rather than one per symbol: a sector is
        two dozen contracts and an index is fifty, and fifty round trips to
        draw one chart is not a chart anybody waits for.
        """
        ...

    async def baselines(self, session: date, symbols: Sequence[str]) -> dict[str, Decimal]:
        """Each symbol's last archived price *before* ``session``.

        The archive stores what traded, not what the previous close was, so an
        archived day's baseline has to be derived: the last price captured on
        the session before it. That is a previous close in every sense that
        matters here, and it is the only one available for a day already gone.
        Symbols with nothing prior are absent rather than zero.
        """
        ...

    async def sessions(self, limit: int) -> list[date]:
        """Archived sessions, newest first — what Historical can offer."""
        ...


@runtime_checkable
class BreadthUniverseSource(Protocol):
    """Which contracts a scope covers, and what the whole board is doing.

    Separate from the history port because it answers a catalog question, not
    an archive one. Keeping them apart is what stops a future in-memory
    history double from having to know about sectors.
    """

    async def scope(self, index: str, sector: str | None) -> BreadthScope:
        """The symbols, weights and benchmark contract for one selection."""
        ...

    async def sector_board(self, tenant_id: TenantId) -> SectorBoard:
        """Every sector of the F&O universe, counted, for the rail."""
        ...

    async def live(self, tenant_id: TenantId, symbols: Sequence[str]) -> LiveReading:
        """Where these contracts stand right now, off the live board.

        Two jobs. It is the only thing that can draw a session the archive has
        not captured yet — the first minutes of a trading day, or a deployment
        whose capture worker has never run. And on a captured day it lets the
        series reach the present instead of stopping at the last sweep, which
        on a one-minute cadence is up to a minute of missing chart.
        """
        ...


@dataclass(frozen=True, slots=True)
class LiveReading:
    """The board as it stands, in the two pieces breadth needs."""

    at: datetime
    prices: list[PricePoint] = field(default_factory=list)
    #: Each contract's previous close, exactly as the broker reports it.
    baselines: dict[str, Decimal] = field(default_factory=dict)
    source: str = "mock"


@dataclass(frozen=True, slots=True)
class BreadthScope:
    """What "NIFTY 50" or "the IT sector" resolves to.

    ``weights`` is empty for a sector: the F&O universe has no published
    weights outside the two tracked indices, and an empty mapping is what
    tells the page to offer no weighted view rather than a flat one.
    """

    label: str
    symbols: tuple[str, ...]
    weights: dict[str, Decimal] = field(default_factory=dict)
    #: The contract whose price is the benchmark line. ``None`` for a sector,
    #: which has no index of its own.
    level_symbol: str | None = None


@dataclass(frozen=True, slots=True)
class SectorBoard:
    """The rail: the tracked indices, then every sector."""

    sectors: list[SectorRow] = field(default_factory=list)
    source: str = "mock"


@runtime_checkable
class InstitutionalFlowSource(Protocol):
    async def read(
        self, tenant_id: TenantId, *, sessions: int, until: date | None = None
    ) -> list[FlowDay]:
        """The last ``sessions`` published participant days, oldest first.

        ``until`` caps the window at an archived session for replay; ``None``
        means up to the most recent published day. Trading holidays simply do
        not appear — the list is sessions, not calendar days, and a consumer
        that assumes otherwise will mis-date its own axis.
        """
        ...

    async def read_open_interest(self, tenant_id: TenantId, session: date) -> list[OiRow]:
        """Participant-wise open interest for one session.

        A separate call from ``read`` because these are separate publications:
        the value tables and the participant-wise OI file are two documents,
        and a source may well have one and not the other. An empty list means
        "nothing published for that session", which the page renders as an
        empty board rather than as zeros.
        """
        ...

    async def neighbours(
        self, tenant_id: TenantId, session: date
    ) -> tuple[date | None, date | None]:
        """The published sessions immediately before and after ``session``.

        ``(None, None)`` at the two ends of the archive. The date stepper on
        the page is built from this rather than from calendar arithmetic of
        its own: only the source knows which days the exchange published, and
        a client guessing "yesterday" walks into every holiday.
        """
        ...

    async def read_index(
        self, tenant_id: TenantId, session: date, index: str
    ) -> IndexSnapshot | None:
        """Where ``index`` closed on ``session``, if this source can say.

        Separate from ``IndexConstituentSource.read`` because it answers a
        different question. The broker answers "where is the index *now*";
        this answers "where did it finish on that day". For the latest
        session the two agree, and for every archived one only this can be
        right — a broker asked about a session three weeks back returns
        today's level, and printing that under that day's date is a lie the
        reader has no way to catch.

        ``None`` when the source has no archived close, which is the ordinary
        answer for a source that only generates figures.
        """
        ...

    @property
    def source(self) -> str:
        """``"live"`` or ``"mock"``.

        Declared on the port rather than inferred by the caller. The daily
        participant file has no real adapter yet, and a generated flow board
        is indistinguishable from a true one by inspection — this property is
        the only thing that separates them.
        """
        ...
