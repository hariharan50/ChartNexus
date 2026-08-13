"""Wire contract for the AI Market Guider.

The domain is plain dataclasses; these Pydantic models give the endpoints a typed,
validated, documented response and a single ``of`` mapping so the route handlers
stay thin. The guidance response now carries a **per-horizon** array (intraday /
end-of-day / swing), each a calibrated call, while keeping the original top-level
fields (echoing the intraday headline) for back-compat with existing readers.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from marketcompass.contexts.signals.application.ports import GuidanceRecord
from marketcompass.contexts.signals.domain.models import (
    HorizonCall,
    Levels,
    MarketContext,
    MultiHorizonGuidance,
    TradeScaffold,
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HorizonCallResponse(_Schema):
    """One horizon's calibrated call — the unit the UI's horizon switcher renders."""

    horizon: str
    decision: str
    #: Model p(up-move) in [0, 1].
    probability: float
    #: Calibrated 0-100 conviction (mapped to measured hit-rate, scaled by coverage).
    confidence: int
    #: The features that moved this call most, strongest first.
    drivers: list[str]

    @classmethod
    def of(cls, call: HorizonCall) -> HorizonCallResponse:
        return cls(
            horizon=call.horizon.value,
            decision=call.decision.value,
            probability=call.probability,
            confidence=call.confidence,
            drivers=list(call.drivers),
        )


class MarketContextResponse(_Schema):
    """The shared backdrop for the console's context cards (VIX, PCR)."""

    india_vix: float | None
    india_vix_change_percent: float | None
    pcr: float | None

    @classmethod
    def of(cls, context: MarketContext) -> MarketContextResponse:
        return cls(
            india_vix=context.india_vix,
            india_vix_change_percent=context.india_vix_change_percent,
            pcr=context.pcr,
        )


class LevelsResponse(_Schema):
    spot: float
    support: float | None
    resistance: float | None
    max_pain: float | None
    gamma_flip: float | None
    call_wall: float | None
    put_wall: float | None

    @classmethod
    def of(cls, levels: Levels) -> LevelsResponse:
        return cls(
            spot=levels.spot,
            support=levels.support,
            resistance=levels.resistance,
            max_pain=levels.max_pain,
            gamma_flip=levels.gamma_flip,
            call_wall=levels.call_wall,
            put_wall=levels.put_wall,
        )


class ScaffoldResponse(_Schema):
    entry: float | None
    stop: float | None
    target: float | None
    risk_reward: float | None
    suggested_contract: str | None

    @classmethod
    def of(cls, scaffold: TradeScaffold) -> ScaffoldResponse:
        return cls(
            entry=scaffold.entry,
            stop=scaffold.stop,
            target=scaffold.target,
            risk_reward=scaffold.risk_reward,
            suggested_contract=scaffold.suggested_contract,
        )


def _headline_score(guidance: MultiHorizonGuidance) -> float:
    """Directional score in [-1, +1] from the intraday probability, for readers
    (and the history strip) that still expect a single scalar."""
    headline = guidance.headline
    if headline is None:
        return 0.0
    return round((headline.probability - 0.5) * 2.0, 4)


class GuidanceResponse(_Schema):
    symbol: str
    #: Headline (intraday) call, echoed at top level for back-compat.
    decision: str
    confidence: int
    score: float
    #: The market regime the call was made in (trending up/down, rangebound).
    regime: str
    #: live / cached / mock — matches the app's DataSourceBadge vocabulary.
    provenance: str
    is_actionable: bool
    rationale: str
    expiry_ref: str | None
    warnings: list[str]
    #: One calibrated call per horizon (intraday / end-of-day / swing).
    horizons: list[HorizonCallResponse]
    #: Shared market backdrop for the context cards (VIX, PCR).
    context: MarketContextResponse
    levels: LevelsResponse
    scaffold: ScaffoldResponse

    @classmethod
    def of(cls, guidance: MultiHorizonGuidance) -> GuidanceResponse:
        headline = guidance.headline
        return cls(
            symbol=guidance.symbol,
            decision=(headline.decision.value if headline else "HOLD"),
            confidence=(headline.confidence if headline else 0),
            score=_headline_score(guidance),
            regime=guidance.regime,
            provenance=guidance.provenance.value,
            is_actionable=guidance.is_actionable,
            rationale=guidance.rationale,
            expiry_ref=guidance.expiry_ref,
            warnings=list(guidance.warnings),
            horizons=[HorizonCallResponse.of(call) for call in guidance.calls],
            context=MarketContextResponse.of(guidance.context),
            levels=LevelsResponse.of(guidance.levels),
            scaffold=ScaffoldResponse.of(guidance.scaffold),
        )


class FactorsResponse(_Schema):
    """The per-horizon calibrated breakdown alone, for the "why" panel."""

    symbol: str
    regime: str
    horizons: list[HorizonCallResponse]

    @classmethod
    def of(cls, guidance: MultiHorizonGuidance) -> FactorsResponse:
        return cls(
            symbol=guidance.symbol,
            regime=guidance.regime,
            horizons=[HorizonCallResponse.of(call) for call in guidance.calls],
        )


class HistoryItemResponse(_Schema):
    generated_at: datetime
    symbol: str
    decision: str
    confidence: int
    score: float
    provenance: str

    @classmethod
    def of(cls, record: GuidanceRecord) -> HistoryItemResponse:
        return cls(
            generated_at=record.generated_at,
            symbol=record.symbol,
            decision=record.decision.value,
            confidence=record.confidence,
            score=record.score,
            provenance=record.provenance.value,
        )


class HistoryResponse(_Schema):
    symbol: str
    items: list[HistoryItemResponse]

    @classmethod
    def of(cls, symbol: str, records: tuple[GuidanceRecord, ...]) -> HistoryResponse:
        return cls(symbol=symbol, items=[HistoryItemResponse.of(r) for r in records])
