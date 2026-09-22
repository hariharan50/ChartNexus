"""A priced index, assembled from the catalog, the weight table and the board.

Implements ``IndexConstituentSource``. The sanctioned bridge for the
market-breadth context: that context owns the breadth, contribution and
rotation maths and declares the port, and this adapter is the only thing that
knows the instrument catalog, the sector map, the weight table and the futures
board all exist.

**Prices come from the futures board, and the pages say so.** The board is one
batched broker read across the whole F&O universe — the same call the Future
Dashboard already makes, so an Analysis page open beside it costs no extra
quota. The alternative, a cash quote per member, is fifty round trips per
refresh against a capped daily allowance, for numbers that differ from these
by the basis. The cost of the choice is real and is not hidden: every
snapshot from here is stamped ``basis="futures"``, and the pages print it.

The index's own level is read the same way, from its index future, so the
header and the member rows are measured on the same market rather than one on
cash and one on futures — a mismatch that would make the contribution residual
look like a modelling error when it was only a basis.
"""

from __future__ import annotations

from decimal import Decimal

from marketcompass.contexts.futures_analytics.application.ports import FuturesBoardSource
from marketcompass.contexts.futures_analytics.domain.buildup import FuturesReading
from marketcompass.contexts.market_breadth.domain.constituents import (
    Constituent,
    IndexSnapshot,
)
from marketcompass.infrastructure.catalog import registry
from marketcompass.infrastructure.catalog.index_weights import (
    INDEX_INSTRUMENTS,
    TRACKED_INDICES,
    weights_for,
)
from marketcompass.infrastructure.catalog.sector_map import INDEX_MEMBERS, sector_for
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.shared_kernel.types.identifiers import TenantId

log = get_logger(__name__)

#: What every snapshot from this adapter is measured on. Named rather than
#: inlined so the reason travels with the value.
BASIS = "futures"


class BoardIndexConstituentSource:
    """Implements the ``IndexConstituentSource`` port."""

    def __init__(self, board: FuturesBoardSource) -> None:
        self._board = board

    def universe(self) -> tuple[str, ...]:
        """Indices with both a membership list and a weight table.

        Both, not either: an index with members and no weights would count
        breadth correctly and then draw an empty weightage donut, which looks
        like a bug rather than like a missing table.
        """
        return tuple(
            index for index in TRACKED_INDICES if index in INDEX_MEMBERS and weights_for(index)
        )

    async def read(self, tenant_id: TenantId, index: str) -> IndexSnapshot:
        wanted = index.strip().upper()
        members = INDEX_MEMBERS.get(wanted, frozenset())
        weights = weights_for(wanted)
        if not members:
            log.warning("breadth_unknown_index", index=wanted)
            return IndexSnapshot(index=wanted, level=None, previous_close=None, basis=BASIS)

        snapshot = await self._board.read(tenant_id)
        readings: dict[str, FuturesReading] = {
            reading.symbol.strip().upper(): reading for reading in snapshot.readings
        }

        priced: list[Constituent] = []
        for symbol in sorted(members):
            reading = readings.get(symbol)
            if reading is None:
                # Omitted rather than carried as a zero-priced row: a member
                # the board never saw has no last price to show, and inventing
                # one would put a fabricated number in a table of real ones.
                # It still counts against `universe` below.
                continue
            priced.append(
                Constituent(
                    symbol=symbol,
                    name=reading.name or _catalog_name(symbol),
                    last=reading.price,
                    previous_close=reading.price_open,
                    weight_percent=weights.get(symbol, Decimal(0)),
                    # The board carries a sector for catalogued names; the map
                    # is the fallback for anything it did not classify.
                    sector=reading.sector or sector_for(symbol),
                )
            )

        level, previous = self._index_level(wanted, readings)
        if len(priced) < len(members):
            log.info(
                "breadth_partial_index",
                index=wanted,
                priced=len(priced),
                universe=len(members),
            )

        return IndexSnapshot(
            index=wanted,
            level=level,
            previous_close=previous,
            members=tuple(priced),
            universe=len(members),
            source=snapshot.source,
            as_of=None,
            basis=BASIS,
        )

    def _index_level(
        self, index: str, readings: dict[str, FuturesReading]
    ) -> tuple[Decimal | None, Decimal | None]:
        """The index's own print, from its future, or ``(None, None)``.

        ``None`` propagates all the way to the page as "no index level", which
        greys the contribution bars rather than scaling them by a guess — the
        contribution maths needs a real baseline and has no business inventing
        one.
        """
        instrument = INDEX_INSTRUMENTS.get(index)
        reading = readings.get(instrument) if instrument else None
        if reading is None:
            return (None, None)
        return (reading.price, reading.price_open)


def _catalog_name(symbol: str) -> str | None:
    """The catalog's descriptive name, when the process has a catalog loaded.

    ``None`` whenever it does not — the registry starts empty and is filled at
    startup, and a page that renders before that should show a bare ticker
    rather than fail.
    """
    instrument = registry.current().find(symbol)
    return instrument.name if instrument else None
