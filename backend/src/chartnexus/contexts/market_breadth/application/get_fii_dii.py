"""The two FII/DII reads.

The Summary page wants one session described completely — value by segment,
participant-wise open interest, and where the index stood. The Cash Market
page wants a window of cash-segment history. Both start from the same windowed
source call, so the two pages cannot disagree about what "today" was across a
session boundary.

The Summary read also resolves the session's **neighbours**, so the page's
date stepper moves between days the exchange actually published rather than
guessing at "yesterday" and landing on a holiday.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from chartnexus.contexts.market_breadth.application.ports import (
    IndexConstituentSource,
    InstitutionalFlowSource,
)
from chartnexus.contexts.market_breadth.domain.constituents import IndexSnapshot
from chartnexus.contexts.market_breadth.domain.flows import (
    CashDay,
    Crore,
    FlowDay,
    Segment,
    SegmentFlow,
    cash_history,
    net_streak,
    window_total,
)
from chartnexus.contexts.market_breadth.domain.open_interest import (
    OiGroup,
    OiRow,
    by_participant,
    by_segment,
    segment_imbalance,
)
from chartnexus.shared_kernel.types.identifiers import TenantId

#: Sessions fetched when the caller does not say. A quarter of trading days —
#: long enough for the cumulative line to show a trend, short enough that the
#: bars stay individually readable.
DEFAULT_SESSIONS = 60
MAX_SESSIONS = 250

#: Rolling windows the Summary page prints beside the latest day. One trading
#: week and one trading month, in sessions.
WEEK_SESSIONS = 5
MONTH_SESSIONS = 22


@dataclass(frozen=True, slots=True)
class FlowQuery:
    tenant_id: TenantId
    sessions: int = DEFAULT_SESSIONS
    #: Archived session to end the window on. ``None`` means the latest
    #: published day.
    until: date | None = None

    @property
    def clamped(self) -> int:
        return max(1, min(self.sessions, MAX_SESSIONS))


@dataclass(frozen=True, slots=True)
class FlowSummary:
    """The latest published session, by segment, with the context around it."""

    session_date: date | None
    segments: tuple[SegmentFlow, ...] = ()
    #: Cash nets over the last week and month of sessions. Cash only: the
    #: derivative segments are not additive with it (see ``Segment``).
    fii_cash_week: Crore = Decimal(0)
    fii_cash_month: Crore = Decimal(0)
    dii_cash_week: Crore = Decimal(0)
    dii_cash_month: Crore = Decimal(0)
    #: Signed run of consecutive same-side cash sessions, ending on the latest.
    fii_cash_streak: int = 0
    dii_cash_streak: int = 0
    #: Sessions the window actually covered, which may be fewer than asked for.
    sessions: int = 0
    source: str = "mock"
    #: Participant-wise open interest for this session, grouped both ways so
    #: the page's view toggle flips between two prepared orderings rather than
    #: re-sorting rows in the browser — which is how the two views end up
    #: disagreeing about a number.
    by_participant: list[OiGroup] = field(default_factory=list)
    by_segment: list[OiGroup] = field(default_factory=list)
    #: How far each segment's nets are from summing to zero. Zero everywhere on
    #: a complete board; surfaced rather than asserted.
    imbalance: dict[str, int] = field(default_factory=dict)
    #: The published sessions either side of this one, for the date stepper.
    #: ``None`` at the ends of the archive.
    previous_session: date | None = None
    next_session: date | None = None
    #: Where the benchmark stood **on this session** — the archived close for
    #: an older day, not today's level under yesterday's date. ``None`` when
    #: no close has been published for it yet.
    index: IndexSnapshot | None = None


@dataclass(frozen=True, slots=True)
class CashFlowHistory:
    """The cash segment across the window, oldest first."""

    days: list[CashDay] = field(default_factory=list)
    fii_total: Crore = Decimal(0)
    dii_total: Crore = Decimal(0)
    source: str = "mock"


#: The benchmark the Summary card prints beside the session date.
SUMMARY_INDEX = "NIFTY50"


@dataclass(slots=True)
class GetFiiDiiSummary:
    source: InstitutionalFlowSource
    #: Optional: the page prints the index level beside the session, and a
    #: deployment without a constituent source should still serve the flow
    #: board rather than fail. ``None`` simply omits that one line.
    index: IndexConstituentSource | None = None

    async def __call__(self, query: FlowQuery) -> FlowSummary:
        days = await self.source.read(query.tenant_id, sessions=query.clamped, until=query.until)
        if not days:
            return FlowSummary(session_date=None, source=self.source.source)

        ordered = sorted(days, key=lambda day: day.session_date)
        latest = ordered[-1]
        session = latest.session_date
        cash = cash_history(ordered)
        fii_nets = [entry.fii_net for entry in cash]
        dii_nets = [entry.dii_net for entry in cash]

        rows: list[OiRow] = await self.source.read_open_interest(query.tenant_id, session)
        previous, following = await self.source.neighbours(query.tenant_id, session)

        return FlowSummary(
            session_date=session,
            segments=_ordered_segments(latest),
            fii_cash_week=window_total(fii_nets, WEEK_SESSIONS),
            fii_cash_month=window_total(fii_nets, MONTH_SESSIONS),
            dii_cash_week=window_total(dii_nets, WEEK_SESSIONS),
            dii_cash_month=window_total(dii_nets, MONTH_SESSIONS),
            fii_cash_streak=net_streak(fii_nets),
            dii_cash_streak=net_streak(dii_nets),
            sessions=len(cash),
            source=self.source.source,
            by_participant=by_participant(rows),
            by_segment=by_segment(rows),
            imbalance=segment_imbalance(rows),
            previous_session=previous,
            next_session=following,
            index=await self._index_for(query, session),
        )

    async def _index_for(self, query: FlowQuery, session: date) -> IndexSnapshot | None:
        """The benchmark, as it stood on the session being shown.

        The flow source is asked first because it answers for *that day*: it
        reads the exchange's own report for the session, so stepping back
        three weeks prints the level that session closed at. The broker
        cannot do this — asked about an archived day it returns the level
        now, which under that day's date is simply false.

        The broker is the fallback for one real gap: between the participant
        file appearing after the close and the market activity report
        following it, the latest session exists with no archived close yet,
        and there the broker's level *is* that session's. It is never used
        for an archived day, where a wrong level is worse than no level, and
        it costs a board fetch against the shared quota only in that window.
        """
        archived = await self.source.read_index(query.tenant_id, session, SUMMARY_INDEX)
        if archived is not None:
            return archived
        if self.index is None or query.until is not None:
            return None
        return await self.index.read(query.tenant_id, SUMMARY_INDEX)


@dataclass(slots=True)
class GetFiiDiiCashHistory:
    source: InstitutionalFlowSource

    async def __call__(self, query: FlowQuery) -> CashFlowHistory:
        days = await self.source.read(query.tenant_id, sessions=query.clamped, until=query.until)
        cash = cash_history(days)
        if not cash:
            return CashFlowHistory(source=self.source.source)
        last = cash[-1]
        return CashFlowHistory(
            days=cash,
            # The running totals already carry the window sum, so this is a
            # read rather than a second pass over the series.
            fii_total=last.fii_cumulative,
            dii_total=last.dii_cumulative,
            source=self.source.source,
        )


#: Segment order on the Summary page. Cash first because it is the one that
#: moves the index; the derivative segments follow index-before-stock, which is
#: how the exchange's own file is laid out.
_SEGMENT_ORDER: tuple[Segment, ...] = (
    Segment.CASH,
    Segment.INDEX_FUTURES,
    Segment.INDEX_OPTIONS,
    Segment.STOCK_FUTURES,
    Segment.STOCK_OPTIONS,
)


def _ordered_segments(day: FlowDay) -> tuple[SegmentFlow, ...]:
    """The day's segments in reading order, skipping any it did not publish."""
    found = {entry.segment: entry for entry in day.segments}
    return tuple(found[name] for name in _SEGMENT_ORDER if name in found)
