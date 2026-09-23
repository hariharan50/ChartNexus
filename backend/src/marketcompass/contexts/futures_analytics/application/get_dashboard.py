"""The Future Dashboard read.

One board fetch, classified once, then sliced into the six panels the page
shows. Deliberately one pass: the panels are views of the same readings, and
computing them independently would let a contract appear as a top gainer in one
card and be missing from the build-up card beside it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from marketcompass.contexts.futures_analytics.application.ports import FuturesBoardSource
from marketcompass.contexts.futures_analytics.domain.buildup import (
    DEFAULT_DEADBAND_PERCENT,
    BuildupRow,
    BuildupState,
    FuturesReading,
    in_state,
    to_rows,
    top_gainers,
    top_losers,
)
from marketcompass.shared_kernel.types.identifiers import TenantId

#: Rows per panel on the dashboard. The reference layout shows five with a
#: "View all" affordance behind it.
DEFAULT_PANEL_LIMIT = 5
MAX_PANEL_LIMIT = 50


@dataclass(frozen=True, slots=True)
class FuturesDashboardQuery:
    tenant_id: TenantId
    limit: int = DEFAULT_PANEL_LIMIT
    sector: str | None = None
    #: "index" or "stock". None means the whole universe.
    kind: str | None = None
    #: Which contract series to draw — 0 near month, 1 next, 2 far.
    series: int = 0
    deadband_percent: Decimal = DEFAULT_DEADBAND_PERCENT


@dataclass(frozen=True, slots=True)
class FuturesDashboard:
    """Every panel, plus the universe it was computed from."""

    rows: list[BuildupRow]
    top_gainers: list[BuildupRow]
    top_losers: list[BuildupRow]
    long_buildup: list[BuildupRow]
    short_buildup: list[BuildupRow]
    short_covering: list[BuildupRow]
    long_unwinding: list[BuildupRow]
    #: How many contracts the board actually priced. Shown, not hidden: a
    #: dashboard drawn from 40 of 219 contracts is a different claim from one
    #: drawn from all of them.
    covered: int
    #: Size of the catalogued universe the board was drawn from.
    universe: int
    #: "live" or "mock" — never let the two be mistaken for each other.
    source: str = "mock"
    #: ISO date of the contract series these rows belong to.
    expiry: str | None = None
    #: Which series was drawn — 0 near month, 1 next, 2 far.
    series: int = 0
    #: Whether open interest was available for it. When false every row is
    #: NEUTRAL and the four build-up panels are empty *because nothing was
    #: measured*, not because nothing happened — a distinction the page has to
    #: make rather than leave the reader to guess at.
    has_open_interest: bool = True


@dataclass(slots=True)
class GetFuturesDashboard:
    source: FuturesBoardSource

    async def __call__(self, query: FuturesDashboardQuery) -> FuturesDashboard:
        snapshot = await self.source.read(query.tenant_id, series=query.series)
        readings = snapshot.readings
        if query.kind:
            wanted_kind = query.kind.strip().casefold()
            readings = [r for r in readings if (r.kind or "").casefold() == wanted_kind]
        if query.sector:
            wanted = query.sector.strip().casefold()
            readings = [r for r in readings if (r.sector or "").casefold() == wanted]

        rows = to_rows(readings, deadband_percent=query.deadband_percent)
        # After filtering, not before: a stocks-only view settles on the NSE
        # date even though three BSE indices in the full universe do not.
        expiry = _modal_expiry(readings) or snapshot.expiry
        limit = max(1, min(query.limit, MAX_PANEL_LIMIT))

        return FuturesDashboard(
            rows=rows,
            top_gainers=top_gainers(rows, limit=limit),
            top_losers=top_losers(rows, limit=limit),
            long_buildup=in_state(rows, BuildupState.LONG_BUILDUP, limit=limit),
            short_buildup=in_state(rows, BuildupState.SHORT_BUILDUP, limit=limit),
            short_covering=in_state(rows, BuildupState.SHORT_COVERING, limit=limit),
            long_unwinding=in_state(rows, BuildupState.LONG_UNWINDING, limit=limit),
            covered=len(rows),
            universe=snapshot.universe,
            source=snapshot.source,
            expiry=expiry,
            series=snapshot.series,
            has_open_interest=snapshot.has_open_interest,
        )


def _modal_expiry(readings: list[FuturesReading]) -> str | None:
    """The expiry most of these contracts share."""
    counts = Counter(reading.expiry for reading in readings if reading.expiry)
    return counts.most_common(1)[0][0] if counts else None
