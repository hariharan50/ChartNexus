"""Market-breadth endpoints — the Future Lab's Analysis subsection.

Six reads behind six pages, in two families:

* **FII/DII** — the exchange's daily participant file, in rupees crore.
* **Index** — one priced index, sliced four ways: who moved it, how broad the
  move was, how the weight is distributed, and where each sector sits
  relative to the index.

The index reads share one snapshot type on purpose. A name that advanced on
Advance/Decline is advancing on Contributors, because both are arithmetic over
the same list of members priced against the same previous close.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from marketcompass.contexts.market_breadth.api.dependencies import Services
from marketcompass.contexts.market_breadth.api.schemas import (
    AdvanceDeclineResponse,
    BreadthSeriesResponse,
    CashFlowResponse,
    ContributorsResponse,
    FlowSummaryResponse,
    SectorRailResponse,
    SectorRotationResponse,
    WeightageResponse,
)
from marketcompass.contexts.market_breadth.application.get_breadth_series import (
    DEFAULT_INTERVAL,
    INTERVALS,
    BreadthSeriesQuery,
)
from marketcompass.contexts.market_breadth.application.get_fii_dii import (
    DEFAULT_SESSIONS,
    MAX_SESSIONS,
    FlowQuery,
)
from marketcompass.contexts.market_breadth.application.get_index_analysis import (
    DEFAULT_INDEX,
    IndexQuery,
)
from marketcompass.infrastructure.transport.http.dependencies import CurrentPrincipal

router = APIRouter(prefix="/breadth", tags=["breadth"])

SessionsParam = Annotated[
    int,
    Query(ge=1, le=MAX_SESSIONS, description="Trading sessions to return, most recent last."),
]
UntilParam = Annotated[
    date | None,
    Query(
        alias="until",
        description="End the window on this archived session. Omit for the latest.",
    ),
]
SessionParam = Annotated[
    date | None,
    Query(
        alias="date",
        description=(
            "The session to describe. Omit for the latest published one. The "
            "response's `previous_session`/`next_session` are the neighbouring "
            "published days — step with those rather than computing a date, or "
            "the first holiday lands on an empty board."
        ),
    ),
]
IndexParam = Annotated[
    str,
    Query(description="Index to analyse. See the source's own universe for valid names."),
]


@router.get(
    "/fii-dii/summary",
    response_model=FlowSummaryResponse,
    summary="The latest published FII/DII session, by segment",
    description=(
        "Gross buy, gross sell and net for FIIs and DIIs in the cash segment "
        "and the four derivative segments, plus rolling cash nets and the run "
        "of consecutive same-side sessions. Figures are rupees crore. The DII "
        "line is null in the derivative segments — the published breakdown "
        "does not carry one, and that is a dash on screen, never a zero. "
        "`by_participant` and `by_segment` carry the same participant-wise "
        "**open interest** board in two groupings, counted in contracts — a "
        "different measurement from the crore figures, and not comparable with "
        "them. The four nets sum to zero in every segment because every long "
        "is somebody's short; `imbalance` publishes any residual. `index` is "
        "present only for the latest session."
    ),
)
async def fii_dii_summary(
    principal: CurrentPrincipal,
    services: Services,
    sessions: SessionsParam = DEFAULT_SESSIONS,
    date_: SessionParam = None,
) -> FlowSummaryResponse:
    result = await services.fii_dii_summary(
        FlowQuery(tenant_id=principal.tenant_id, sessions=sessions, until=date_)
    )
    return FlowSummaryResponse.of(result)


@router.get(
    "/fii-dii/cash",
    response_model=CashFlowResponse,
    summary="Cash-market FII/DII activity over a window of sessions",
    description=(
        "One row per trading session, oldest first, in rupees crore. "
        "`fii_cumulative` and `dii_cumulative` are running totals **from the "
        "first session in this window**, not from any absolute epoch — a "
        "windowed chart can only answer a windowed question."
    ),
)
async def fii_dii_cash(
    principal: CurrentPrincipal,
    services: Services,
    sessions: SessionsParam = DEFAULT_SESSIONS,
    until: UntilParam = None,
) -> CashFlowResponse:
    result = await services.fii_dii_cash(
        FlowQuery(tenant_id=principal.tenant_id, sessions=sessions, until=until)
    )
    return CashFlowResponse.of(result)


@router.get(
    "/index/contributors",
    response_model=ContributorsResponse,
    summary="Index points contributed by each member",
    description=(
        "`points = weight/100 x change%/100 x previous index level`, with the "
        "priced members' weights renormalised to sum to 100 so the bars add up "
        "to the number in the page header. `header.covered_weight_percent` "
        "says how much of the index that actually was, and `gap` publishes the "
        "residual against the index's own move rather than hiding it."
    ),
)
async def index_contributors(
    principal: CurrentPrincipal,
    services: Services,
    index: IndexParam = DEFAULT_INDEX,
) -> ContributorsResponse:
    result = await services.contributors(_index_query(principal, services, index))
    return ContributorsResponse.of(result)


@router.get(
    "/index/advance-decline",
    response_model=AdvanceDeclineResponse,
    summary="How many index members are up, down and flat",
    description=(
        "Counted overall, per sector, and listed member by member. A move "
        "inside the deadband counts as unchanged rather than as direction; "
        "members the feed could not price are counted as `unpriced`, which is "
        "a different fact from `unchanged`."
    ),
)
async def advance_decline(
    principal: CurrentPrincipal,
    services: Services,
    index: IndexParam = DEFAULT_INDEX,
) -> AdvanceDeclineResponse:
    result = await services.advance_decline(_index_query(principal, services, index))
    return AdvanceDeclineResponse.of(result)


SectorParam = Annotated[
    str | None,
    Query(
        max_length=64,
        description=(
            "Narrow the series to one sector of the F&O universe. Omit for the "
            "index itself. A sector carries no index weights and no benchmark "
            "level, and the response says so."
        ),
    ),
]
BreadthSessionParam = Annotated[
    date | None,
    Query(
        alias="date",
        description="Archived session to replay. Omit for today, which is Live.",
    ),
]
BreadthIntervalParam = Annotated[
    str,
    Query(description=f"Bucket width: {', '.join(INTERVALS)}."),
]


@router.get(
    "/index/advance-decline/series",
    response_model=BreadthSeriesResponse,
    summary="Advances and declines through the session",
    description=(
        "How many members of an index — or of one sector — were above their "
        "baseline, once per bucket across a trading day, with the benchmark's "
        "level beside it. "
        "**Counted out of the futures-board archive after the fact**: nothing "
        "in this application stores breadth, and the board is captured every "
        "minute for the whole F&O universe. `quality` therefore matters — see "
        "its description — and `baseline` says which previous close each point "
        "was measured against. "
        "Weighted figures are present only when the scope has published index "
        "weights, which no sector does."
    ),
)
async def advance_decline_series(  # noqa: PLR0917 — FastAPI reads the
    # parameters to build the query-string contract; collapsing them into one
    # object would take those names out of the OpenAPI schema.
    principal: CurrentPrincipal,
    services: Services,
    index: IndexParam = DEFAULT_INDEX,
    sector: SectorParam = None,
    date_: BreadthSessionParam = None,
    interval: BreadthIntervalParam = DEFAULT_INTERVAL,
) -> BreadthSeriesResponse:
    result = await services.breadth_series(
        BreadthSeriesQuery(
            tenant_id=principal.tenant_id,
            index=_known_index(services, index),
            sector=sector,
            session=date_,
            interval=interval if interval in INTERVALS else DEFAULT_INTERVAL,
        )
    )
    return BreadthSeriesResponse.of(result)


@router.get(
    "/sectors",
    response_model=SectorRailResponse,
    summary="Every sector of the F&O universe, counted",
    description=(
        "The Advance/Decline page's rail. Counts come from one board read "
        "across the whole catalog — the same call the Future Dashboard makes, "
        "so this costs no extra broker quota. "
        "`mean_change_percent` is **unweighted**: these are all listed F&O "
        "names, most of which belong to no tracked index and carry no "
        "published weight. `sessions` lists the days Historical can actually "
        "draw, taken from the archive rather than from a calendar."
    ),
)
async def sector_rail(
    principal: CurrentPrincipal,
    services: Services,
) -> SectorRailResponse:
    return SectorRailResponse.of(await services.sector_rail(principal.tenant_id))


@router.get(
    "/index/weightage",
    response_model=WeightageResponse,
    summary="How the index's weight is distributed",
    description=(
        "Free-float weight per member and per sector, from the catalog's "
        "hand-maintained table, with each one's current move beside it. "
        "`share_percent` is the weight renormalised over the priced members — "
        "that is what a donut of these slices actually draws."
    ),
)
async def index_weightage(
    principal: CurrentPrincipal,
    services: Services,
    index: IndexParam = DEFAULT_INDEX,
) -> WeightageResponse:
    result = await services.weightage(_index_query(principal, services, index))
    return WeightageResponse.of(result)


@router.get(
    "/sector-rotation",
    response_model=SectorRotationResponse,
    summary="Each sector's strength and participation against its index",
    description=(
        "`relative_strength` is the sector's weight-averaged move minus the "
        "index's own; `participation_percent` is the share of its members "
        "advancing. **Not a classical RRG** — the second axis is "
        "participation, not momentum, because a rate-of-change axis needs "
        "weeks of stored constituent history this application does not keep "
        "yet. It is a single-session snapshot with no tail."
    ),
)
async def sector_rotation(
    principal: CurrentPrincipal,
    services: Services,
    index: IndexParam = DEFAULT_INDEX,
) -> SectorRotationResponse:
    result = await services.sector_rotation(_index_query(principal, services, index))
    return SectorRotationResponse.of(result)


def _known_index(services: Services, index: str) -> str:
    """The index name, validated — same 404 as ``_index_query``, no query."""
    wanted = index.strip().upper()
    known = services.indices()
    if wanted not in known:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown index {index!r}. Tracked: {', '.join(known)}.",
        )
    return wanted


def _index_query(principal: CurrentPrincipal, services: Services, index: str) -> IndexQuery:
    """Validate the index name against what the source can actually answer for.

    A 404 rather than an empty board: asking for an index nobody tracks is a
    different thing from asking for one whose members could not be priced, and
    a page that cannot tell them apart will show "no data" for a typo.
    """
    return IndexQuery(tenant_id=principal.tenant_id, index=_known_index(services, index))
