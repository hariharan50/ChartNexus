"""Wire shapes for the PMS endpoint.

Three conventions the client depends on, two shared with GIA and one specific
to this page:

* **Decimals serialise as strings**, parsed client-side through its own
  ``toNumber``. Nothing does float arithmetic on a price on the way out.
* **``null`` means unknown, never zero.** A figure that did not arrive renders
  as a dash. Coercing it to 0 turns "we do not know" into "it did not move".
* **Every percentage ships with its denominator.** Breadth carries counts, the
  regime carries ``inputs_present``/``inputs_total``, and the VIX percentile
  carries its sample size. A screener that prints a bare percentage invites the
  reader to trust a number that eleven observations cannot support.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from marketcompass.contexts.pre_market.domain.expected_move import ExpectedMove, MoveEstimate
from marketcompass.contexts.pre_market.domain.gap import Gap
from marketcompass.contexts.pre_market.domain.readings import (
    BreadthReading,
    FlowReading,
    GlobalReading,
    NarrativeReading,
    OptionsReading,
)
from marketcompass.contexts.pre_market.domain.regime import AxisRead, Factor, Regime
from marketcompass.contexts.pre_market.domain.view import (
    HeadlineIndex,
    LevelMap,
    PreMarketView,
    SectionStatus,
    SectionStatuses,
    Technicals,
    Volatility,
)
from marketcompass.shared_kernel.domain.levels import Level, LevelCluster


class _Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StatusResponse(_Schema):
    availability: str
    reason: str | None

    @classmethod
    def of(cls, status: SectionStatus) -> StatusResponse:
        return cls(availability=status.availability.value, reason=status.reason)


class StatusesResponse(_Schema):
    headline: StatusResponse
    levels: StatusResponse
    technicals: StatusResponse
    volatility: StatusResponse
    expected_move: StatusResponse
    options: StatusResponse
    global_cues: StatusResponse
    breadth: StatusResponse
    flows: StatusResponse
    regime: StatusResponse
    narrative: StatusResponse

    @classmethod
    def of(cls, statuses: SectionStatuses) -> StatusesResponse:
        return cls(
            headline=StatusResponse.of(statuses.headline),
            levels=StatusResponse.of(statuses.levels),
            technicals=StatusResponse.of(statuses.technicals),
            volatility=StatusResponse.of(statuses.volatility),
            expected_move=StatusResponse.of(statuses.expected_move),
            options=StatusResponse.of(statuses.options),
            global_cues=StatusResponse.of(statuses.global_cues),
            breadth=StatusResponse.of(statuses.breadth),
            flows=StatusResponse.of(statuses.flows),
            regime=StatusResponse.of(statuses.regime),
            narrative=StatusResponse.of(statuses.narrative),
        )


class GapResponse(_Schema):
    points: Decimal
    percent: Decimal
    bucket: str
    #: ``atr`` or ``percent`` — which yardstick produced the bucket. Carried
    #: because the same gap buckets differently against a wide-range index.
    basis: str
    atr_multiple: float | None
    reference_close: Decimal

    @classmethod
    def of(cls, gap: Gap | None) -> GapResponse | None:
        if gap is None:
            return None
        return cls(
            points=gap.points,
            percent=gap.percent,
            bucket=gap.bucket.value,
            basis=gap.basis.value,
            atr_multiple=gap.atr_multiple,
            reference_close=gap.reference_close,
        )


class HeadlineResponse(_Schema):
    symbol: str
    label: str
    price: Decimal | None
    change: Decimal | None
    change_percent: Decimal | None
    previous_close: Decimal | None
    gap: GapResponse | None
    #: Only NIFTY has an overnight contract; the other two are always null.
    implied_gap: GapResponse | None
    breadth_tracked: bool
    source: str

    @classmethod
    def of(cls, card: HeadlineIndex) -> HeadlineResponse:
        return cls(
            symbol=card.symbol,
            label=card.label,
            price=card.price,
            change=card.change,
            change_percent=card.change_percent,
            previous_close=card.previous_close,
            gap=GapResponse.of(card.gap),
            implied_gap=GapResponse.of(card.implied_gap),
            breadth_tracked=card.breadth_tracked,
            source=card.source,
        )


class LevelResponse(_Schema):
    label: str
    price: float
    origin: str
    side: str
    distance_points: float
    distance_percent: float
    distance_atr: float | None

    @classmethod
    def of(cls, level: Level) -> LevelResponse:
        return cls(
            label=level.label,
            price=level.price,
            origin=level.origin.value,
            side=level.side.value,
            distance_points=level.distance.points,
            distance_percent=level.distance.percent,
            distance_atr=level.distance.atr_multiple,
        )


class ClusterResponse(_Schema):
    """Levels from independent methods that agree — the panel's real finding."""

    price: float
    labels: list[str]
    origins: list[str]

    @classmethod
    def of(cls, item: LevelCluster) -> ClusterResponse:
        return cls(
            price=item.price,
            labels=[member.label for member in item.members],
            origins=[origin.value for origin in item.origins],
        )


class RangeResponse(_Schema):
    high: float
    low: float
    #: How many bars went into it. A 52-week high off eleven bars is not one.
    bars: int


class LevelsResponse(_Schema):
    spot: float
    pivot: float | None
    r1: float | None
    r2: float | None
    r3: float | None
    s1: float | None
    s2: float | None
    s3: float | None
    cpr_top: float | None
    cpr_bottom: float | None
    cpr_width_percent: float | None
    prior_day_high: float | None
    prior_day_low: float | None
    prior_day_close: float | None
    week: RangeResponse | None
    month: RangeResponse | None
    year: RangeResponse | None
    ladder: list[LevelResponse]
    clusters: list[ClusterResponse]
    nearest_above: LevelResponse | None
    nearest_below: LevelResponse | None

    @classmethod
    def of(cls, levels: LevelMap | None) -> LevelsResponse | None:
        if levels is None:
            return None
        pivots = levels.pivots
        cpr = levels.central_pivot
        return cls(
            spot=levels.spot,
            pivot=pivots.pivot if pivots else None,
            r1=pivots.r1 if pivots else None,
            r2=pivots.r2 if pivots else None,
            r3=pivots.r3 if pivots else None,
            s1=pivots.s1 if pivots else None,
            s2=pivots.s2 if pivots else None,
            s3=pivots.s3 if pivots else None,
            cpr_top=cpr.top if cpr else None,
            cpr_bottom=cpr.bottom if cpr else None,
            cpr_width_percent=cpr.width_percent if cpr else None,
            prior_day_high=levels.prior_day_high,
            prior_day_low=levels.prior_day_low,
            prior_day_close=levels.prior_day_close,
            week=RangeResponse.model_validate(levels.week) if levels.week else None,
            month=RangeResponse.model_validate(levels.month) if levels.month else None,
            year=RangeResponse.model_validate(levels.year) if levels.year else None,
            ladder=[LevelResponse.of(item) for item in levels.levels],
            clusters=[ClusterResponse.of(item) for item in levels.clusters],
            nearest_above=LevelResponse.of(levels.nearest_above)
            if levels.nearest_above
            else None,
            nearest_below=LevelResponse.of(levels.nearest_below)
            if levels.nearest_below
            else None,
        )


class TechnicalsResponse(_Schema):
    ema20: float | None
    ema50: float | None
    ema100: float | None
    ema200: float | None
    #: ``null`` for a mixed stack — "the averages disagree" is a real state.
    ema_stacked_up: bool | None
    rsi14: float | None
    adx14: float | None
    atr14: float | None
    atr_percent: float | None
    bollinger_width: float | None
    realized_vol20: float | None

    @classmethod
    def of(cls, read: Technicals | None) -> TechnicalsResponse | None:
        return cls.model_validate(read) if read else None


class VolatilityResponse(_Schema):
    india_vix: Decimal | None
    india_vix_change_percent: Decimal | None
    vix_percentile: float | None
    #: Printed beside the percentile, always. It is why the rank may be null.
    vix_sample_sessions: int
    atm_iv: Decimal | None
    iv_percentile: Decimal | None

    @classmethod
    def of(cls, read: Volatility | None) -> VolatilityResponse | None:
        return cls.model_validate(read) if read else None


class MoveResponse(_Schema):
    basis: str
    points: float
    percent: float
    upper: float
    lower: float

    @classmethod
    def of(cls, estimate: MoveEstimate | None) -> MoveResponse | None:
        return cls.model_validate(estimate) if estimate else None


class ExpectedMoveResponse(_Schema):
    """Three measures, never blended — see the domain module for why."""

    spot: float
    straddle: MoveResponse | None
    vix: MoveResponse | None
    atr: MoveResponse | None
    days_to_expiry: int | None
    note: str | None

    @classmethod
    def of(cls, move: ExpectedMove | None) -> ExpectedMoveResponse | None:
        if move is None:
            return None
        return cls(
            spot=move.spot,
            straddle=MoveResponse.of(move.straddle),
            vix=MoveResponse.of(move.vix),
            atr=MoveResponse.of(move.atr),
            days_to_expiry=move.days_to_expiry,
            note=move.note,
        )


class OptionsResponse(_Schema):
    days_to_expiry: int | None
    atm_strike: Decimal | None
    pcr_oi: Decimal | None
    pcr_change: Decimal | None
    total_call_oi: int | None
    total_put_oi: int | None
    max_pain: Decimal | None
    call_wall: Decimal | None
    put_wall: Decimal | None
    gamma_flip: Decimal | None
    atm_iv: Decimal | None
    atm_straddle: Decimal | None

    @classmethod
    def of(cls, read: OptionsReading | None) -> OptionsResponse | None:
        return cls.model_validate(read) if read else None


class ContributionResponse(_Schema):
    key: str
    label: str
    region: str
    change_percent: Decimal
    points: Decimal


class GiftResponse(_Schema):
    level: Decimal | None
    change: Decimal | None
    change_percent: Decimal | None
    overnight_high: Decimal | None
    overnight_low: Decimal | None
    gap_points: Decimal | None
    gap_percent: Decimal | None
    signal: str | None


class GlobalCuesResponse(_Schema):
    pressure_score: Decimal | None
    pressure_band: str | None
    contributions: list[ContributionResponse]
    #: Weighted markets with no quote. A composite built from four of nine
    #: inputs is a different claim from one built on all nine.
    missing: list[str]
    macro: list[ContributionResponse]
    gift: GiftResponse | None

    @classmethod
    def of(cls, read: GlobalReading | None) -> GlobalCuesResponse | None:
        if read is None:
            return None
        return cls(
            pressure_score=read.pressure_score,
            pressure_band=read.pressure_band,
            contributions=[
                ContributionResponse.model_validate(item) for item in read.contributions
            ],
            missing=list(read.missing),
            macro=[ContributionResponse.model_validate(item) for item in read.macro],
            gift=GiftResponse.model_validate(read.gift) if read.gift else None,
        )


class BreadthResponse(_Schema):
    advances: int | None
    declines: int | None
    unchanged: int | None
    #: The denominator. Twelve BANK NIFTY members move a percentage in 8.3%
    #: steps, and a bare percentage would read as precision it does not have.
    priced: int | None
    universe: int | None

    @classmethod
    def of(cls, read: BreadthReading | None) -> BreadthResponse | None:
        return cls.model_validate(read) if read else None


class FlowsResponse(_Schema):
    session_date: str | None
    fii_net: Decimal | None
    dii_net: Decimal | None

    @classmethod
    def of(cls, read: FlowReading | None) -> FlowsResponse | None:
        if read is None:
            return None
        return cls(
            session_date=read.session_date.isoformat() if read.session_date else None,
            fii_net=read.fii_net,
            dii_net=read.dii_net,
        )


class FactorResponse(_Schema):
    key: str
    label: str
    axis: str
    stance: str
    points: float
    #: The raw input. Non-negotiable: without it the score cannot be argued
    #: with, and a composite nobody can argue with is a horoscope.
    reading: str
    note: str | None

    @classmethod
    def of(cls, item: Factor) -> FactorResponse:
        return cls(
            key=item.key,
            label=item.label,
            axis=item.axis.value,
            stance=item.stance.value,
            points=item.points,
            reading=item.reading,
            note=item.note,
        )


class AxisResponse(_Schema):
    axis: str
    label: str
    stance: str
    points: float
    resolved: bool
    factors: list[FactorResponse]

    @classmethod
    def of(cls, item: AxisRead) -> AxisResponse:
        return cls(
            axis=item.axis.value,
            label=item.label,
            stance=item.stance.value,
            points=item.points,
            resolved=item.resolved,
            factors=[FactorResponse.of(factor) for factor in item.factors],
        )


class RegimeResponse(_Schema):
    score: float
    band: str
    #: Coverage, not conviction. A lopsided score off three inputs is thin.
    confidence: str
    inputs_present: int
    inputs_total: int
    axes: list[AxisResponse]
    factors: list[FactorResponse]

    @classmethod
    def of(cls, regime: Regime | None) -> RegimeResponse | None:
        if regime is None:
            return None
        return cls(
            score=regime.score,
            band=regime.band.value,
            confidence=regime.confidence,
            inputs_present=regime.inputs_present,
            inputs_total=regime.inputs_total,
            axes=[AxisResponse.of(axis) for axis in regime.axes],
            factors=[FactorResponse.of(factor) for factor in regime.factors],
        )


class NarrativeResponse(_Schema):
    markdown: str
    trading_day: str
    generated_at: str | None
    source: str

    @classmethod
    def of(cls, read: NarrativeReading | None) -> NarrativeResponse | None:
        if read is None:
            return None
        return cls(
            markdown=read.markdown,
            trading_day=read.trading_day.isoformat(),
            generated_at=read.generated_at.isoformat() if read.generated_at else None,
            source=read.source,
        )


class PhaseResponse(_Schema):
    is_open: bool
    session_date: str
    time_ist: str
    opens_ist: str
    closes_ist: str


class PreMarketViewResponse(_Schema):
    as_of: str
    phase: PhaseResponse
    focus: str
    focus_label: str
    #: The weakest leg's provenance. A page is only as live as its least live
    #: input, and claiming otherwise is how simulated numbers get traded on.
    source: str
    status: StatusesResponse
    headline: list[HeadlineResponse]
    levels: LevelsResponse | None
    technicals: TechnicalsResponse | None
    volatility: VolatilityResponse | None
    expected_move: ExpectedMoveResponse | None
    options: OptionsResponse | None
    global_cues: GlobalCuesResponse | None
    breadth: BreadthResponse | None
    flows: FlowsResponse | None
    regime: RegimeResponse | None
    narrative: NarrativeResponse | None

    @classmethod
    def of(cls, view: PreMarketView) -> PreMarketViewResponse:
        return cls(
            as_of=view.as_of.isoformat(),
            phase=PhaseResponse.model_validate(view.phase),
            focus=view.focus,
            focus_label=view.focus_label,
            source=view.source,
            status=StatusesResponse.of(view.status),
            headline=[HeadlineResponse.of(card) for card in view.headline],
            levels=LevelsResponse.of(view.levels),
            technicals=TechnicalsResponse.of(view.technicals),
            volatility=VolatilityResponse.of(view.volatility),
            expected_move=ExpectedMoveResponse.of(view.expected_move),
            options=OptionsResponse.of(view.options),
            global_cues=GlobalCuesResponse.of(view.global_cues),
            breadth=BreadthResponse.of(view.breadth),
            flows=FlowsResponse.of(view.flows),
            regime=RegimeResponse.of(view.regime),
            narrative=NarrativeResponse.of(view.narrative),
        )
