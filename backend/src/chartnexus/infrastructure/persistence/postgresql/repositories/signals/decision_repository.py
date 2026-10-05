"""The one place signal decisions are written and read.

Implements the signals context's ``GuidanceRepositoryPort``. It maps the pure
``Guidance`` aggregate onto the ``signal_decisions`` table and back into the thin
``GuidanceRecord`` the history endpoint returns — the table's shape is known in
exactly this module, mirroring how the option-chain repository is structured.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chartnexus.contexts.signals.application.ports import GuidanceRecord
from chartnexus.contexts.signals.domain.models import Decision, Guidance, Provenance
from chartnexus.infrastructure.persistence.postgresql.models.signals.signal_decision import (
    SignalDecisionRecord,
)
from chartnexus.infrastructure.time.clock import SystemClock
from chartnexus.shared_kernel.types.identifiers import TenantId


class SqlAlchemySignalDecisionRepository:
    """Writes and reads AI-guider decisions for one tenant at a time."""

    def __init__(self, session: AsyncSession, *, clock: SystemClock | None = None) -> None:
        self._session = session
        self._clock = clock or SystemClock()

    async def latest(self, tenant_id: TenantId, symbol: str) -> GuidanceRecord | None:
        stmt = (
            select(SignalDecisionRecord)
            .where(
                SignalDecisionRecord.tenant_id == tenant_id,
                SignalDecisionRecord.symbol == symbol,
            )
            .order_by(SignalDecisionRecord.generated_at.desc())
            .limit(1)
        )
        record = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if record is None else _to_record(record)

    async def save(self, tenant_id: TenantId, guidance: Guidance) -> GuidanceRecord:
        record = SignalDecisionRecord(
            tenant_id=tenant_id,
            symbol=guidance.symbol,
            generated_at=self._clock.now(),
            decision=guidance.decision.value,
            confidence=guidance.confidence,
            score=Decimal(str(guidance.score)),
            components=[_skill_json(skill) for skill in guidance.skills],
            entry=_num(guidance.scaffold.entry),
            stop=_num(guidance.scaffold.stop),
            target=_num(guidance.scaffold.target),
            risk_reward=_num(guidance.scaffold.risk_reward),
            suggested_contract=guidance.scaffold.suggested_contract,
            provenance_source=guidance.provenance.value,
            expiry_ref=guidance.expiry_ref,
            is_actionable=guidance.is_actionable,
        )
        self._session.add(record)
        await self._session.flush()
        return _to_record(record)

    async def history(
        self, tenant_id: TenantId, symbol: str, *, limit: int
    ) -> tuple[GuidanceRecord, ...]:
        stmt = (
            select(SignalDecisionRecord)
            .where(
                SignalDecisionRecord.tenant_id == tenant_id,
                SignalDecisionRecord.symbol == symbol,
            )
            .order_by(SignalDecisionRecord.generated_at.desc())
            .limit(limit)
        )
        records = (await self._session.execute(stmt)).scalars().all()
        return tuple(_to_record(record) for record in records)


def _to_record(record: SignalDecisionRecord) -> GuidanceRecord:
    return GuidanceRecord(
        generated_at=record.generated_at,
        symbol=record.symbol,
        decision=Decision(record.decision),
        confidence=record.confidence,
        score=float(record.score),
        provenance=Provenance(record.provenance_source),
    )


def _skill_json(skill: object) -> dict[str, object]:
    # ``skill`` is a domain SkillRead; read structurally to keep that type out of
    # the persistence signature.
    return {
        "skill": getattr(skill, "skill", ""),
        "label": getattr(skill, "label", ""),
        "weight": getattr(skill, "weight", 0.0),
        "score": getattr(skill, "score", None),
        "headline": getattr(skill, "headline", ""),
        "details": list(getattr(skill, "details", ())),
    }


def _num(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))
