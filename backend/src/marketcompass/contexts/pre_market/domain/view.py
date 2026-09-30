"""The aggregate the page renders, and the per-section honesty that holds it up.

One read, one instant — the same rule ``GetGlobalView`` states for GIA, and it
matters more here. A regime score computed from an 09:04 quote set, sitting
beside a level ladder drawn from an 09:06 one and a gap card from 09:02, will
disagree with itself for reasons no user can diagnose. Eleven polled endpoints
guarantee that screenshot. One endpoint and one ``as_of`` prevent it.

**``SectionStatus`` is a domain concept, not a scatter of try/except.** This
page reads from four upstream contexts and any of them can be down. Making
availability part of the model means a dead option chain degrades one panel
with a stated reason, rather than blanking a page a trader is about to act on —
and it makes the failure states unit-testable, which a scatter of exception
handlers never is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from marketcompass.contexts.pre_market.domain.expected_move import ExpectedMove
from marketcompass.contexts.pre_market.domain.gap import Gap
from marketcompass.contexts.pre_market.domain.readings import (
    BreadthReading,
    FlowReading,
    GlobalReading,
    MarketPhase,
    NarrativeReading,
    OptionsReading,
)
from marketcompass.contexts.pre_market.domain.regime import Regime
from marketcompass.shared_kernel.domain.levels import (
    CentralPivot,
    Level,
    LevelCluster,
    PivotSet,
    PriceRange,
)


class Availability(StrEnum):
    OK = "ok"
    #: Answered, but not with everything asked for — a partial board, a stale
    #: cache. The panel renders with a caveat rather than pretending.
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class SectionStatus:
    """Whether one panel's data arrived, and why not when it did not."""

    availability: Availability
    reason: str | None = None

    @classmethod
    def ok(cls) -> SectionStatus:
        return cls(availability=Availability.OK)

    @classmethod
    def degraded(cls, reason: str) -> SectionStatus:
        return cls(availability=Availability.DEGRADED, reason=reason)

    @classmethod
    def unavailable(cls, reason: str) -> SectionStatus:
        return cls(availability=Availability.UNAVAILABLE, reason=reason)

    @property
    def resolved(self) -> bool:
        return self.availability is not Availability.UNAVAILABLE


@dataclass(frozen=True, slots=True)
class HeadlineIndex:
    """One of the three cards across the top."""

    symbol: str
    label: str
    price: Decimal | None
    change: Decimal | None
    change_percent: Decimal | None
    previous_close: Decimal | None
    #: The realised gap, once the market has opened. ``None`` before it does —
    #: and deliberately not backfilled from GIFT, which is a quote, not a print.
    gap: Gap | None
    #: What GIFT is quoting for the open. Only meaningful for NIFTY; the other
    #: two have no overnight contract of their own.
    implied_gap: Gap | None
    breadth_tracked: bool
    source: str


@dataclass(frozen=True, slots=True)
class Technicals:
    """Where the focused index sits on its own daily chart."""

    ema20: float | None
    ema50: float | None
    ema100: float | None
    ema200: float | None
    #: ``True`` when 20 > 50 > 100 > 200, ``False`` when fully inverted,
    #: ``None`` when the stack is mixed or the history is too thin to say.
    ema_stacked_up: bool | None
    rsi14: float | None
    adx14: float | None
    atr14: float | None
    atr_percent: float | None
    bollinger_width: float | None
    realized_vol20: float | None


@dataclass(frozen=True, slots=True)
class LevelMap:
    """Every reference price, ordered, with the spot's place among them."""

    spot: float
    pivots: PivotSet | None
    central_pivot: CentralPivot | None
    prior_day_high: float | None
    prior_day_low: float | None
    prior_day_close: float | None
    week: PriceRange | None
    month: PriceRange | None
    year: PriceRange | None
    #: Ordered high to low, so the client renders a ladder without sorting.
    levels: tuple[Level, ...]
    clusters: tuple[LevelCluster, ...]
    nearest_above: Level | None
    nearest_below: Level | None


@dataclass(frozen=True, slots=True)
class Volatility:
    """India VIX and the option book's own implied volatility."""

    india_vix: Decimal | None
    india_vix_change_percent: Decimal | None
    #: ``None`` until enough sessions have accrued. Printed beside the
    #: percentile so nobody reads a rank off eleven observations.
    vix_percentile: float | None
    vix_sample_sessions: int
    atm_iv: Decimal | None
    iv_percentile: Decimal | None


@dataclass(frozen=True, slots=True)
class SectionStatuses:
    """One flag per panel. Absent from this list means the panel is not built."""

    headline: SectionStatus
    levels: SectionStatus
    technicals: SectionStatus
    volatility: SectionStatus
    expected_move: SectionStatus
    options: SectionStatus
    global_cues: SectionStatus
    breadth: SectionStatus
    flows: SectionStatus
    regime: SectionStatus
    narrative: SectionStatus


@dataclass(frozen=True, slots=True)
class PreMarketView:
    """Everything the PMS page renders, from one instant."""

    as_of: datetime
    phase: MarketPhase
    focus: str
    focus_label: str
    source: str
    status: SectionStatuses
    headline: tuple[HeadlineIndex, ...]
    levels: LevelMap | None
    technicals: Technicals | None
    volatility: Volatility | None
    expected_move: ExpectedMove | None
    options: OptionsReading | None
    global_cues: GlobalReading | None
    breadth: BreadthReading | None
    flows: FlowReading | None
    regime: Regime | None
    narrative: NarrativeReading | None
