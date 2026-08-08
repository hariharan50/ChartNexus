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
