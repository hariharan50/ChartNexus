"""The captured session and the F&O universe, for breadth.

Two adapters, both sanctioned bridges of the same kind as
``constituent_source``: the ``market_breadth`` context declares the ports and
owns the counting, and these are the only modules that know the futures board's
archive, the instrument catalog, the sector map and the weight table all exist.

The translation that matters is the archive's. There is no stored breadth
history anywhere in this application — what exists is a minute-by-minute
capture of the *futures board*, written for the Future Lab's price charts, and
a breadth series is counted out of it after the fact. That is why
``BoardFrame`` becomes ``PricePoint`` here: the context must not learn that its
history happens to be somebody else's.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Protocol

from marketcompass.contexts.futures_analytics.application.ports import (
    BoardFrame,
    FuturesBoardSource,
)
from marketcompass.contexts.futures_analytics.domain.buildup import FuturesReading
from marketcompass.contexts.market_breadth.application.ports import (
    BreadthScope,
    LiveReading,
    SectorBoard,
)
from marketcompass.contexts.market_breadth.domain.breadth import sector_board
from marketcompass.contexts.market_breadth.domain.breadth_series import PricePoint
from marketcompass.contexts.market_breadth.domain.constituents import Constituent
from marketcompass.infrastructure.catalog import registry
from marketcompass.infrastructure.catalog.index_weights import (
    INDEX_INSTRUMENTS,
    label_for,
    weights_for,
)
from marketcompass.infrastructure.catalog.sector_map import INDEX_MEMBERS, sector_for
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.shared_kernel.types.identifiers import TenantId

log = get_logger(__name__)


class ArchiveReader(Protocol):
    """The three archive queries breadth needs.

    Declared here rather than taken as the whole repository: this adapter uses
    three of its nine methods, and saying so keeps a test double to three.
    """

    async def frames_for_session(
        self, session_date: date, symbols: Sequence[str]
    ) -> list[BoardFrame]: ...

    async def last_price_before(
        self, session_date: date, symbols: Sequence[str]
    ) -> dict[str, Decimal]: ...

    async def archived_sessions(self, limit: int) -> list[date]: ...


class ArchiveBreadthHistorySource:
    """Implements ``BreadthHistorySource`` over the futures-board archive."""

    def __init__(self, archive: ArchiveReader) -> None:
        self._archive = archive

    async def prices(self, session: date, symbols: Sequence[str]) -> list[PricePoint]:
        frames = await self._archive.frames_for_session(session, symbols)
        return [
            PricePoint(symbol=frame.symbol, at=frame.captured_at, price=frame.price)
            for frame in frames
        ]

    async def baselines(self, session: date, symbols: Sequence[str]) -> dict[str, Decimal]:
        return await self._archive.last_price_before(session, symbols)

    async def sessions(self, limit: int) -> list[date]:
        return await self._archive.archived_sessions(limit)


class CatalogBreadthUniverseSource:
    """Implements ``BreadthUniverseSource`` from the catalog and the board."""

    def __init__(self, board: FuturesBoardSource) -> None:
        self._board = board

    async def scope(self, index: str, sector: str | None) -> BreadthScope:
        """Resolve a rail selection into contracts, weights and a benchmark.

        An **index** scope carries its published weights and its own future as
        the benchmark line. A **sector** scope carries neither: its members are
        every F&O name the sector map classifies there, most of which sit in no
        tracked index, so there is no weight to average and no sector future to
        price. The empty mapping is the signal, not a flag beside it.
        """
        wanted = index.strip().upper()
        if sector:
            return BreadthScope(
                label=sector,
                symbols=tuple(sorted(_symbols_in(sector))),
            )

        members = INDEX_MEMBERS.get(wanted, frozenset())
        weights = weights_for(wanted)
        level = INDEX_INSTRUMENTS.get(wanted)
        # The index's own future rides along in the symbol list so one archive
        # query fetches the benchmark with the members; it is excluded from the
        # counts by simply having no baseline of its own in the member set.
        symbols = tuple(sorted(members)) + ((level,) if level else ())
        return BreadthScope(
            label=label_for(wanted),
            symbols=symbols,
            weights=dict(weights),
            level_symbol=level,
        )

    async def sector_board(self, tenant_id: TenantId) -> SectorBoard:
        """Every sector of the F&O universe, counted off one board read.

        The same board call the Future Dashboard makes, so the rail costs no
        extra broker quota. Readings become ``Constituent`` rows with **zero
        weight**, which is the truth: an F&O name outside NIFTY 50 and BANK
        NIFTY has no published index weight, and the domain's ``sector_board``
        takes a plain mean precisely because of that.
        """
        snapshot = await self._board.read(tenant_id)
        members = [_as_constituent(reading) for reading in snapshot.readings]
        return SectorBoard(
            sectors=sector_board(members),
            source=snapshot.source,
        )

    async def live(self, tenant_id: TenantId, symbols: Sequence[str]) -> LiveReading:
        """The board now, narrowed to one scope.

        Baselines here are the broker's own previous close, which is the exact
        figure — unlike the archive's derived one. The series says which it
        used, because on a thin contract the two differ.
        """
        wanted = {symbol.strip().upper() for symbol in symbols}
        snapshot = await self._board.read(tenant_id)
        prices: list[PricePoint] = []
        baselines: dict[str, Decimal] = {}
        now = datetime.now(UTC)
        for reading in snapshot.readings:
            if reading.symbol not in wanted:
                continue
            prices.append(PricePoint(symbol=reading.symbol, at=now, price=reading.price))
            if reading.price_open is not None:
                baselines[reading.symbol] = reading.price_open
        return LiveReading(at=now, prices=prices, baselines=baselines, source=snapshot.source)


def _symbols_in(sector: str) -> set[str]:
    """Every catalogued F&O name the sector map puts in this sector."""
    wanted = sector.strip().upper()
    return {
        row.symbol
        for row in registry.current().all()
        if (row.sector or sector_for(row.symbol) or "").strip().upper() == wanted
    }


def _as_constituent(reading: FuturesReading) -> Constituent:
    """A board reading as a countable member, weightless.

    Zero weight is the honest value, not a placeholder: this is the whole F&O
    universe, and a name outside the two tracked indices has no published
    index weight at all. The domain's ``sector_board`` averages unweighted for
    exactly this reason.
    """
    return Constituent(
        symbol=reading.symbol,
        name=reading.name,
        last=reading.price,
        previous_close=reading.price_open,
        weight_percent=Decimal(0),
        sector=reading.sector or sector_for(reading.symbol),
    )
