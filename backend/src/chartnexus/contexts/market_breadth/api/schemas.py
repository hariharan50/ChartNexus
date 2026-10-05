"""Wire shapes for the Future Lab Analysis pages.

Every money figure is rupees crore and every ``*_percent`` is already scaled
0-100 — the client formats, it never converts. Nullable fields mean "not
known", and the client must render them as a dash rather than as zero.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from chartnexus.contexts.market_breadth.application.get_breadth_series import (
    BreadthSeries,
    SectorRail,
)
from chartnexus.contexts.market_breadth.application.get_fii_dii import (
    CashFlowHistory,
    FlowSummary,
)
from chartnexus.contexts.market_breadth.application.get_index_analysis import (
    AdvanceDeclineResult,
    ContributorsResult,
    IndexHeader,
    SectorRotationResult,
    WeightageResult,
)
from chartnexus.contexts.market_breadth.domain.breadth import (
    BreadthCount,
    SectorBreadth,
    SectorRow,
)
from chartnexus.contexts.market_breadth.domain.breadth_series import BreadthPoint
from chartnexus.contexts.market_breadth.domain.constituents import Constituent
from chartnexus.contexts.market_breadth.domain.contribution import (
    Contribution,
    WeightSlice,
)
from chartnexus.contexts.market_breadth.domain.flows import (
    CashDay,
    ParticipantFlow,
    SegmentFlow,
)
from chartnexus.contexts.market_breadth.domain.open_interest import (
    FutureLegs,
    OiGroup,
    OiRow,
    OptionLegs,
)
from chartnexus.contexts.market_breadth.domain.rotation import SectorPosition

# -- FII/DII -----------------------------------------------------------------


class ParticipantFlowResponse(BaseModel):
    """One participant's gross buy and sell, in rupees crore."""

    buy: Decimal
    sell: Decimal
    net: Decimal

    @classmethod
    def of(cls, flow: ParticipantFlow) -> ParticipantFlowResponse:
        return cls(buy=flow.buy, sell=flow.sell, net=flow.net)


class SegmentFlowResponse(BaseModel):
    """One segment's activity on one session."""

    segment: str = Field(
        description="cash | index_futures | index_options | stock_futures | stock_options"
    )
    fii: ParticipantFlowResponse
    #: Null for every derivative segment: the published breakdown carries no
    #: DII line there. Render as a dash, never as zero.
    dii: ParticipantFlowResponse | None = None

    @classmethod
    def of(cls, flow: SegmentFlow) -> SegmentFlowResponse:
        return cls(
            segment=flow.segment.value,
            fii=ParticipantFlowResponse.of(flow.fii),
            dii=None if flow.dii is None else ParticipantFlowResponse.of(flow.dii),
        )


class OiLegsResponse(BaseModel):
    """The book behind a net, in contracts.

    Futures fill ``long``/``short``; options fill the four option legs. The
    other pair is null rather than zero — an options book has no "long"
    column, and a zero there would read as an empty one.
    """

    long: int | None = None
    short: int | None = None
    call_long: int | None = None
    call_short: int | None = None
    put_long: int | None = None
    put_short: int | None = None
    total: int = Field(description="Every contract held, both sides.")

    @classmethod
    def of(cls, legs: FutureLegs | OptionLegs) -> OiLegsResponse:
        if isinstance(legs, OptionLegs):
            return cls(
                call_long=legs.call_long,
                call_short=legs.call_short,
                put_long=legs.put_long,
                put_short=legs.put_short,
                total=legs.total,
            )
        return cls(long=legs.long, short=legs.short, total=legs.total)


class OiRowResponse(BaseModel):
    """One participant's position in one segment, in contracts."""

    participant: str = Field(description="fii | dii | pro | client")
    segment: str = Field(
        description="index_futures | index_options | stock_futures | stock_options"
    )
    net: int
    previous_net: int
    change: int = Field(description="net - previous_net, in contracts.")
    #: Null when the source published a net with no breakdown behind it.
    legs: OiLegsResponse | None = None

    @classmethod
    def of(cls, row: OiRow) -> OiRowResponse:
        return cls(
            participant=row.participant.value,
            segment=row.segment.value,
            net=row.net,
            previous_net=row.previous_net,
            change=row.change,
            legs=None if row.legs is None else OiLegsResponse.of(row.legs),
        )


class OiGroupResponse(BaseModel):
    """One band of the board — a participant's segments, or a segment's
    participants, depending on which grouping this came from."""

    key: str
    rows: list[OiRowResponse] = Field(default_factory=list)
    net: int = 0
    change: int = 0

    @classmethod
    def of(cls, group: OiGroup) -> OiGroupResponse:
        return cls(
            key=group.key,
            rows=[OiRowResponse.of(row) for row in group.rows],
            net=group.net,
            change=group.change,
        )


class SummaryIndexResponse(BaseModel):
    """Where the benchmark stood on this session.

    Present only for the latest session: the index close for an archived day
    is not stored, and today's level under yesterday's date would be worse
    than showing nothing.
    """

    index: str
    level: Decimal | None = None
    change_percent: Decimal | None = None
    source: str = Field(default="mock", description="live | mock")
    basis: str = Field(default="cash", description="cash | futures")


class FlowSummaryResponse(BaseModel):
    """The latest published session by segment, with the context around it."""

    session_date: date | None = None
    segments: list[SegmentFlowResponse] = Field(default_factory=list)
    fii_cash_week: Decimal = Decimal(0)
    fii_cash_month: Decimal = Decimal(0)
    dii_cash_week: Decimal = Decimal(0)
    dii_cash_month: Decimal = Decimal(0)
    fii_cash_streak: int = Field(
        default=0,
        description="Signed run of same-side cash sessions: +4 is four days of buying.",
    )
    dii_cash_streak: int = 0
    sessions: int = Field(default=0, description="Sessions the window actually covered.")
    source: str = Field(default="mock", description="live | mock")
    #: Participant-wise open interest, in **contracts** — a different
    #: measurement from the crore figures above, prepared in both groupings so
    #: the page's view toggle never re-sorts rows itself.
    by_participant: list[OiGroupResponse] = Field(default_factory=list)
    by_segment: list[OiGroupResponse] = Field(default_factory=list)
    imbalance: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "How far each segment's four nets are from summing to zero. Zero "
            "everywhere on a complete board — every long is somebody's short."
        ),
    )
    previous_session: date | None = Field(
        default=None, description="The published session before this one, for the stepper."
    )
    next_session: date | None = Field(
        default=None, description="The published session after this one; null at the latest."
    )
    index: SummaryIndexResponse | None = None

    @classmethod
    def of(cls, result: FlowSummary) -> FlowSummaryResponse:
        return cls(
            session_date=result.session_date,
            segments=[SegmentFlowResponse.of(entry) for entry in result.segments],
            fii_cash_week=result.fii_cash_week,
            fii_cash_month=result.fii_cash_month,
            dii_cash_week=result.dii_cash_week,
            dii_cash_month=result.dii_cash_month,
            fii_cash_streak=result.fii_cash_streak,
            dii_cash_streak=result.dii_cash_streak,
            sessions=result.sessions,
            source=result.source,
            by_participant=[OiGroupResponse.of(g) for g in result.by_participant],
            by_segment=[OiGroupResponse.of(g) for g in result.by_segment],
            imbalance=result.imbalance,
            previous_session=result.previous_session,
            next_session=result.next_session,
            index=(
                None
                if result.index is None
                else SummaryIndexResponse(
                    index=result.index.index,
                    level=result.index.level,
                    change_percent=result.index.change_percent,
                    source=result.index.source,
                    basis=result.index.basis,
                )
            ),
        )


class CashDayResponse(BaseModel):
    """One session's cash-segment activity, with the window's running total."""

    session_date: date
    fii_buy: Decimal
    fii_sell: Decimal
    fii_net: Decimal
    dii_buy: Decimal
    dii_sell: Decimal
    dii_net: Decimal
    #: Running net since the first session **in this window**, not since any
    #: absolute epoch.
    fii_cumulative: Decimal
    dii_cumulative: Decimal

    @classmethod
    def of(cls, day: CashDay) -> CashDayResponse:
        return cls(
            session_date=day.session_date,
            fii_buy=day.fii_buy,
            fii_sell=day.fii_sell,
            fii_net=day.fii_net,
            dii_buy=day.dii_buy,
            dii_sell=day.dii_sell,
            dii_net=day.dii_net,
            fii_cumulative=day.fii_cumulative,
            dii_cumulative=day.dii_cumulative,
        )


class CashFlowResponse(BaseModel):
    """The cash segment across the requested window, oldest first."""

    days: list[CashDayResponse] = Field(default_factory=list)
    fii_total: Decimal = Decimal(0)
    dii_total: Decimal = Decimal(0)
    source: str = Field(default="mock", description="live | mock")

    @classmethod
    def of(cls, result: CashFlowHistory) -> CashFlowResponse:
        return cls(
            days=[CashDayResponse.of(day) for day in result.days],
            fii_total=result.fii_total,
            dii_total=result.dii_total,
            source=result.source,
        )


# -- index -------------------------------------------------------------------


class IndexHeaderResponse(BaseModel):
    """The index itself, and how much of it the reading covers."""

    index: str
    level: Decimal | None = None
    previous_close: Decimal | None = None
    change_absolute: Decimal | None = None
    change_percent: Decimal | None = None
    covered: int = Field(default=0, description="Members that produced a usable reading.")
    universe: int = Field(default=0, description="Members the index holds.")
    covered_weight_percent: Decimal = Field(
        default=Decimal(0),
        description="Index weight those members account for. 94 means 6% went unpriced.",
    )
    source: str = Field(default="mock", description="live | mock")
    as_of: str | None = None
    basis: str = Field(
        default="cash",
        description=(
            "Which market the member prices came from: cash prints, or the "
            "front-month future. A future tracks its underlying closely and "
            "diverges with the basis, so the page names which it is showing."
        ),
    )

    @classmethod
    def of(cls, header: IndexHeader) -> IndexHeaderResponse:
        return cls(
            index=header.index,
            level=header.level,
            previous_close=header.previous_close,
            change_absolute=header.change_absolute,
            change_percent=header.change_percent,
            covered=header.covered,
            universe=header.universe,
            covered_weight_percent=header.covered_weight_percent,
            source=header.source,
            as_of=header.as_of,
            basis=header.basis,
        )


class ContributionResponse(BaseModel):
    """One member's push on the index."""

    symbol: str
    name: str | None = None
    sector: str | None = None
    last: Decimal
    change_percent: Decimal
    weight_percent: Decimal = Field(
        description="Renormalised over the priced members, so these sum to 100."
    )
    points: Decimal = Field(description="Index points this member pushed the index.")

    @classmethod
    def of(cls, row: Contribution) -> ContributionResponse:
        return cls(
            symbol=row.symbol,
            name=row.name,
            sector=row.sector,
            last=row.last,
            change_percent=row.change_percent,
            weight_percent=row.weight_percent,
            points=row.points,
        )


class ContributorsResponse(BaseModel):
    """Who pushed the index up, who dragged it down, and by how much."""

    header: IndexHeaderResponse
    gainers: list[ContributionResponse] = Field(default_factory=list)
    losers: list[ContributionResponse] = Field(default_factory=list)
    modelled_points: Decimal = Decimal(0)
    actual_points: Decimal | None = None
    gap: Decimal | None = Field(
        default=None,
        description=(
            "Index move minus the modelled contributions. Near zero on a fully "
            "priced index; published rather than hidden when it is not."
        ),
    )

    @classmethod
    def of(cls, result: ContributorsResult) -> ContributorsResponse:
        board = result.board
        return cls(
            header=IndexHeaderResponse.of(result.header),
            gainers=[ContributionResponse.of(row) for row in board.gainers],
            losers=[ContributionResponse.of(row) for row in board.losers],
            modelled_points=board.modelled_points,
            actual_points=board.actual_points,
            gap=board.gap,
        )


class BreadthCountResponse(BaseModel):
    """Advancing, declining, unchanged — and the ones with no price at all."""

    advancing: int = 0
    declining: int = 0
    unchanged: int = 0
    #: Distinct from ``unchanged``: "did not move" and "we do not know" are
    #: different facts and must not be merged.
    unpriced: int = 0
    ratio: Decimal | None = Field(
        default=None, description="Advances per decline; null when nothing declined."
    )
    advancing_percent: Decimal | None = None
    net: int = 0

    @classmethod
    def of(cls, count: BreadthCount) -> BreadthCountResponse:
        return cls(
            advancing=count.advancing,
            declining=count.declining,
            unchanged=count.unchanged,
            unpriced=count.unpriced,
            ratio=count.ratio,
            advancing_percent=count.advancing_percent,
            net=count.net,
        )


class MemberResponse(BaseModel):
    """One index member as the tables show it."""

    symbol: str
    name: str | None = None
    sector: str | None = None
    last: Decimal
    previous_close: Decimal | None = None
    change_absolute: Decimal | None = None
    change_percent: Decimal | None = None
    weight_percent: Decimal = Decimal(0)

    @classmethod
    def of(cls, member: Constituent) -> MemberResponse:
        return cls(
            symbol=member.symbol,
            name=member.name,
            sector=member.sector,
            last=member.last,
            previous_close=member.previous_close,
            change_absolute=member.change_absolute,
            change_percent=member.change_percent,
            weight_percent=member.weight_percent,
        )


class SectorBreadthResponse(BaseModel):
    """One sector's slice of the index, counted and weighted."""

    sector: str
    count: BreadthCountResponse
    weight_percent: Decimal = Decimal(0)
    weighted_change_percent: Decimal | None = None
    members: list[MemberResponse] = Field(default_factory=list)

    @classmethod
    def of(cls, sector: SectorBreadth) -> SectorBreadthResponse:
        return cls(
            sector=sector.sector,
            count=BreadthCountResponse.of(sector.count),
            weight_percent=sector.weight_percent,
            weighted_change_percent=sector.weighted_change_percent,
            members=[MemberResponse.of(member) for member in sector.members],
        )


class BreadthPointResponse(BaseModel):
    """One bucket of a session's breadth."""

    at: str = Field(description="ISO-8601 instant, UTC.")
    advancing: int
    declining: int
    unchanged: int
    net: int = Field(description="advancing - declining.")
    level: Decimal | None = Field(
        default=None,
        description=(
            "The benchmark's level in this bucket. Null for a sector, which "
            "has no index of its own — never a basket level invented to fill "
            "the field."
        ),
    )
    advancing_weight: Decimal | None = None
    declining_weight: Decimal | None = Field(
        default=None,
        description=(
            "Combined index weight advancing/declining, 0-100. Null when the "
            "scope carries no weights, which is every sector: an F&O name "
            "outside a tracked index has no published weight."
        ),
    )

    @classmethod
    def of(cls, point: BreadthPoint) -> BreadthPointResponse:
        return cls(
            at=point.at.isoformat(),
            advancing=point.advancing,
            declining=point.declining,
            unchanged=point.unchanged,
            net=point.net,
            level=point.level,
            advancing_weight=point.advancing_weight,
            declining_weight=point.declining_weight,
        )


class BreadthSeriesResponse(BaseModel):
    """One scope's session, counted bucket by bucket."""

    label: str
    session: str
    interval: str
    quality: str = Field(
        description=(
            "intraday | live_proxy | empty. `intraday` is the captured "
            "session. `live_proxy` is two points — the open and now — for a "
            "day the archive has not reached, so the line between them is a "
            "join, not a shape. `empty` means there is nothing to draw."
        )
    )
    points: list[BreadthPointResponse] = Field(default_factory=list)
    universe: int = Field(description="Contracts in the scope.")
    measured: int = Field(description="Of those, how many had a baseline.")
    baseline: str = Field(
        description=(
            "previous_close | archived_close. The second is derived from the "
            "prior session's last capture, which is what an archived day has; "
            "on a thin contract the two differ."
        )
    )
    weighted_available: bool
    source: str = Field(default="mock", description="live | mock")

    @classmethod
    def of(cls, series: BreadthSeries) -> BreadthSeriesResponse:
        return cls(
            label=series.label,
            session=series.session.isoformat(),
            interval=series.interval,
            quality=series.quality.value,
            points=[BreadthPointResponse.of(point) for point in series.points],
            universe=series.universe,
            measured=series.measured,
            baseline=series.baseline,
            weighted_available=series.weighted_available,
            source=series.source,
        )


class SectorRowResponse(BaseModel):
    """One sector of the F&O universe, for the rail."""

    sector: str
    count: BreadthCountResponse
    mean_change_percent: Decimal | None = Field(
        default=None,
        description=(
            "Unweighted mean move of the priced members. Unweighted because "
            "these names have no index weight to average with — this is the "
            "whole F&O list, not an index."
        ),
    )
    members: int
    rows: list[MemberResponse] = Field(
        default_factory=list,
        description="The sector's own names, biggest mover first.",
    )

    @classmethod
    def of(cls, row: SectorRow) -> SectorRowResponse:
        return cls(
            sector=row.sector,
            count=BreadthCountResponse.of(row.count),
            mean_change_percent=row.mean_change_percent,
            members=row.members,
            rows=[MemberResponse.of(member) for member in row.rows],
        )


class SectorRailResponse(BaseModel):
    """What the Advance/Decline page's rail offers."""

    indices: list[str] = Field(default_factory=list)
    sectors: list[SectorRowResponse] = Field(default_factory=list)
    sessions: list[str] = Field(
        default_factory=list,
        description=(
            "Archived sessions Historical can draw, newest first. From the "
            "archive, not a calendar: a day nobody captured cannot be drawn."
        ),
    )
    source: str = Field(default="mock", description="live | mock")

    @classmethod
    def of(cls, rail: SectorRail) -> SectorRailResponse:
        return cls(
            indices=list(rail.indices),
            sectors=[SectorRowResponse.of(row) for row in rail.sectors],
            sessions=[session.isoformat() for session in rail.sessions],
            source=rail.source,
        )


class AdvanceDeclineResponse(BaseModel):
    """Index breadth overall, by sector, and member by member."""

    header: IndexHeaderResponse
    overall: BreadthCountResponse
    sectors: list[SectorBreadthResponse] = Field(default_factory=list)
    members: list[MemberResponse] = Field(default_factory=list)

    @classmethod
    def of(cls, result: AdvanceDeclineResult) -> AdvanceDeclineResponse:
        return cls(
            header=IndexHeaderResponse.of(result.header),
            overall=BreadthCountResponse.of(result.overall),
            sectors=[SectorBreadthResponse.of(entry) for entry in result.sectors],
            members=[MemberResponse.of(member) for member in result.members],
        )


class WeightSliceResponse(BaseModel):
    """One row of the Weightage page."""

    label: str
    name: str | None = None
    weight_percent: Decimal
    share_percent: Decimal = Field(description="Share of the priced index — what the donut draws.")
    change_percent: Decimal | None = None
    members: int = 1

    @classmethod
    def of(cls, row: WeightSlice) -> WeightSliceResponse:
        return cls(
            label=row.label,
            name=row.name,
            weight_percent=row.weight_percent,
            share_percent=row.share_percent,
            change_percent=row.change_percent,
            members=row.members,
        )


class WeightageResponse(BaseModel):
    """Index weight by member and by sector."""

    header: IndexHeaderResponse
    members: list[WeightSliceResponse] = Field(default_factory=list)
    sectors: list[SectorBreadthResponse] = Field(default_factory=list)

    @classmethod
    def of(cls, result: WeightageResult) -> WeightageResponse:
        return cls(
            header=IndexHeaderResponse.of(result.header),
            members=[WeightSliceResponse.of(row) for row in result.members],
            sectors=[SectorBreadthResponse.of(entry) for entry in result.sectors],
        )


class SectorPositionResponse(BaseModel):
    """One plotted sector on the rotation chart."""

    sector: str
    change_percent: Decimal
    relative_strength: Decimal = Field(
        description="Sector move minus the index move, in percentage points — the x axis."
    )
    participation_percent: Decimal = Field(
        description="Share of the sector's priced members advancing, 0-100."
    )
    participation_offset: Decimal = Field(
        description="participation_percent - 50, so the origin is neutral — the y axis."
    )
    weight_percent: Decimal
    advancing: int = 0
    declining: int = 0
    members: int = 0
    quadrant: str = Field(description="leading | improving | weakening | lagging")
    leaders: list[str] = Field(default_factory=list)
    laggards: list[str] = Field(default_factory=list)

    @classmethod
    def of(cls, position: SectorPosition) -> SectorPositionResponse:
        return cls(
            sector=position.sector,
            change_percent=position.change_percent,
            relative_strength=position.relative_strength,
            participation_percent=position.participation_percent,
            participation_offset=position.participation_offset,
            weight_percent=position.weight_percent,
            advancing=position.advancing,
            declining=position.declining,
            members=position.members,
            quadrant=position.quadrant.value,
            leaders=list(position.leaders),
            laggards=list(position.laggards),
        )


class SectorRotationResponse(BaseModel):
    """Every sector's position relative to its index, this session."""

    header: IndexHeaderResponse
    sectors: list[SectorPositionResponse] = Field(default_factory=list)

    @classmethod
    def of(cls, result: SectorRotationResult) -> SectorRotationResponse:
        return cls(
            header=IndexHeaderResponse.of(result.header),
            sectors=[SectorPositionResponse.of(entry) for entry in result.sectors],
        )
