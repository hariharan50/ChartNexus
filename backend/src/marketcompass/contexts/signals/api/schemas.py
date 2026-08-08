"""Wire contract for the AI Market Guider.

The domain is plain dataclasses; these Pydantic models give the endpoints a typed,
validated, documented response and a single ``from_domain`` mapping so the route
handlers stay thin.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from marketcompass.contexts.signals.application.ports import GuidanceRecord
from marketcompass.contexts.signals.domain.models import Guidance, Levels, SkillRead, TradeScaffold


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SkillReadResponse(_Schema):
    skill: str
    label: str
    weight: float
    #: ``None`` when the skill had no usable data — the UI greys the card.
    score: float | None
    headline: str
    details: list[str]

    @classmethod
    def of(cls, read: SkillRead) -> SkillReadResponse:
        return cls(
            skill=read.skill,
            label=read.label,
            weight=read.weight,
            score=read.score,
            headline=read.headline,
            details=list(read.details),
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


class GuidanceResponse(_Schema):
    symbol: str
    decision: str
    confidence: int
    score: float
    #: live / cached / mock — matches the app's DataSourceBadge vocabulary.
    provenance: str
    is_actionable: bool
    rationale: str
    expiry_ref: str | None
    warnings: list[str]
    skills: list[SkillReadResponse]
    levels: LevelsResponse
    scaffold: ScaffoldResponse

    @classmethod
    def of(cls, guidance: Guidance) -> GuidanceResponse:
        return cls(
            symbol=guidance.symbol,
            decision=guidance.decision.value,
            confidence=guidance.confidence,
            score=guidance.score,
            provenance=guidance.provenance.value,
            is_actionable=guidance.is_actionable,
            rationale=guidance.rationale,
            expiry_ref=guidance.expiry_ref,
            warnings=list(guidance.warnings),
            skills=[SkillReadResponse.of(read) for read in guidance.skills],
            levels=LevelsResponse.of(guidance.levels),
            scaffold=ScaffoldResponse.of(guidance.scaffold),
        )


class FactorsResponse(_Schema):
    """The per-skill breakdown alone, for the "why" panel."""

    symbol: str
    decision: str
    score: float
    skills: list[SkillReadResponse]

    @classmethod
    def of(cls, guidance: Guidance) -> FactorsResponse:
        return cls(
            symbol=guidance.symbol,
            decision=guidance.decision.value,
            score=guidance.score,
            skills=[SkillReadResponse.of(read) for read in guidance.skills],
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
