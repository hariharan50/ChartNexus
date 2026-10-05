"""The vocabulary the guider speaks.

Pure value objects — no framework, no I/O. A ``Guidance`` is the whole of what
the AI Console renders: a directional call, how sure the engine is, the per-skill
breakdown that call was fused from, an illustrative trade scaffold, and — never
optional — the provenance of the data underneath it.

The domain is deliberately free of the market-data adapter types. Skills are fed
plain numbers through :mod:`signals.application.ports`, so this module and every
skill under :mod:`signals.domain.skills` stay trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Decision(StrEnum):
    """The explicit call. HOLD is a real answer, not a missing one."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Horizon(StrEnum):
    """The time frame a call is made over. Each has its own calibrated model."""

    INTRADAY = "intraday"  # next ~15-30 min
    END_OF_DAY = "end_of_day"  # into the close
    SWING = "swing"  # 1-3 days


class Provenance(StrEnum):
    """The worst data source that fed a decision.

    Mirrors ``market_data.domain.DataSource`` by value so the wire contract and
    the frontend ``DataSourceBadge`` need no translation. It is redeclared here
    rather than imported because a bounded context may not import another's
    package — the values are the contract, and they match on purpose.
    """

    LIVE = "live"
    CACHED = "cached"
    MOCK = "mock"

    @property
    def is_real(self) -> bool:
        return self is not Provenance.MOCK

    @classmethod
    def worst(cls, sources: list[Provenance]) -> Provenance:
        """The least-trustworthy source in the set — MOCK beats CACHED beats LIVE.

        A decision is only as trustworthy as its shakiest input: one mock leg
        makes the whole call mock. An empty set is treated as MOCK — nothing
        real fed it, so nothing about it is safe to trade.
        """
        if not sources:
            return cls.MOCK
        order = {cls.LIVE: 0, cls.CACHED: 1, cls.MOCK: 2}
        return max(sources, key=lambda source: order[source])


@dataclass(frozen=True, slots=True)
class SkillRead:
    """One trading skill's read of the current tape.

    ``score`` is the directional vote in ``[-1, +1]`` (bearish → bullish), or
    ``None`` when the skill had no usable data this session — a missing read
    must drop out of the fusion, never be counted as a neutral zero. ``weight``
    is ``0.0`` for a non-directional skill (Risk Management), which still renders
    a card but casts no vote.
    """

    skill: str
    label: str
    weight: float
    score: float | None
    headline: str
    details: tuple[str, ...] = ()

    @property
    def votes(self) -> bool:
        """True when this read should be counted in the weighted vote."""
        return self.score is not None and self.weight > 0.0


@dataclass(frozen=True, slots=True)
class Levels:
    """The reference prices the Level-Based skill reads support/resistance off.

    Every field is nullable: a one-sided book has no wall, a symmetric one no
    flip, and a mock session may price none of them. ``None`` says "unknown",
    which the UI must draw differently from a level sitting at zero.
    """

    spot: float
    support: float | None = None
    resistance: float | None = None
    max_pain: float | None = None
    gamma_flip: float | None = None
    call_wall: float | None = None
    put_wall: float | None = None


@dataclass(frozen=True, slots=True)
class TradeScaffold:
    """An illustrative entry/stop/target — never an order ticket.

    Built only for a BUY or SELL call, from OI walls and ATR. ``None`` fields
    mean the scaffold could not be anchored (e.g. no wall on the stop side and
    no ATR), and ``suggested_contract`` is a human-readable label, not a
    tradeable symbol. The app places no orders; this is decoration on a read.
    """

    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    risk_reward: float | None = None
    suggested_contract: str | None = None


@dataclass(frozen=True, slots=True)
class HorizonCall:
    """One horizon's calibrated directional call.

    ``probability`` is the model's p(up-move) in ``[0, 1]``; ``confidence`` is the
    calibrated 0-100 read (mapped through the fitted calibration to the measured
    hit-rate, scaled by feature coverage). ``drivers`` are the few features that
    moved the call most, for the breakdown card.
    """

    horizon: Horizon
    decision: Decision
    probability: float
    confidence: int
    drivers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MarketContext:
    """The shared market backdrop the guidance was read against.

    Straight off the same snapshot that fed the engine — India VIX (level and its
    day-change %) and the total put/call ratio — so the console can show the
    context cards without a second round-trip. Every field is nullable: a mock or
    thin session prices none of them.
    """

    india_vix: float | None = None
    india_vix_change_percent: float | None = None
    pcr: float | None = None


@dataclass(frozen=True, slots=True)
class MultiHorizonGuidance:
    """The whole calibrated answer — a call per horizon plus the shared context.

    ``calls`` is one :class:`HorizonCall` per :class:`Horizon`. The top-level
    ``decision``/``confidence`` echo the intraday call so existing readers (and
    the persisted history) keep working; the levels, scaffold, regime and
    provenance are shared across horizons.
    """

    symbol: str
    calls: tuple[HorizonCall, ...]
    regime: str
    provenance: Provenance
    levels: Levels
    scaffold: TradeScaffold
    rationale: str
    context: MarketContext = field(default_factory=MarketContext)
    expiry_ref: str | None = None
    is_actionable: bool = True
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def call_for(self, horizon: Horizon) -> HorizonCall | None:
        return next((c for c in self.calls if c.horizon is horizon), None)

    @property
    def headline(self) -> HorizonCall | None:
        """The intraday call — what the top-level decision/confidence echo."""
        return self.call_for(Horizon.INTRADAY) or (self.calls[0] if self.calls else None)


@dataclass(frozen=True, slots=True)
class Guidance:
    """The whole answer the AI Console renders for one symbol at one moment."""

    symbol: str
    decision: Decision
    confidence: int
    score: float
    provenance: Provenance
    skills: tuple[SkillRead, ...]
    levels: Levels
    scaffold: TradeScaffold
    rationale: str
    expiry_ref: str | None = None
    # Illustrative-only calls are downgraded (e.g. a mock session): the call is
    # still shown, but the UI must state it cannot be traded on.
    is_actionable: bool = True
    warnings: tuple[str, ...] = field(default_factory=tuple)
