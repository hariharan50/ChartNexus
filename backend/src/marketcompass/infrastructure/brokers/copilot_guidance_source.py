"""Feeds the copilot context the current guidance without it importing ``signals``.

Satisfies copilot's ``GuidancePort`` by calling the signals ``GetGuidance`` use
case and translating its ``Guidance`` aggregate into copilot's own
``GuidanceSnapshot``. Lives in ``infrastructure/brokers`` — the sanctioned
cross-context bridge location — so the independence contract stays green.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.copilot.application.ports import GuidancePort
from marketcompass.contexts.copilot.domain.models import GuidanceSnapshot, SkillSnapshot
from marketcompass.contexts.signals.api.dependencies import build_signals_services
from marketcompass.contexts.signals.application.get_guidance import GetGuidance
from marketcompass.contexts.signals.domain.models import Guidance
from marketcompass.shared_kernel.types.identifiers import TenantId


class SignalsGuidanceSource:
    """Implements copilot's ``GuidancePort`` over the signals use case."""

    def __init__(self, *, guidance: GetGuidance) -> None:
        self._guidance = guidance

    async def current(self, tenant_id: TenantId, symbol: str) -> GuidanceSnapshot:
        result = await self._guidance(tenant_id, symbol)
        return _to_snapshot(result)


def _to_snapshot(guidance: Guidance) -> GuidanceSnapshot:
    return GuidanceSnapshot(
        symbol=guidance.symbol,
        decision=guidance.decision.value,
        confidence=guidance.confidence,
        provenance=guidance.provenance.value,
        is_actionable=guidance.is_actionable,
        rationale=guidance.rationale,
        skills=tuple(
            SkillSnapshot(label=read.label, score=read.score, headline=read.headline)
            for read in guidance.skills
        ),
        support=guidance.levels.support,
        resistance=guidance.levels.resistance,
        entry=guidance.scaffold.entry,
        stop=guidance.scaffold.stop,
        target=guidance.scaffold.target,
        suggested_contract=guidance.scaffold.suggested_contract,
        warnings=guidance.warnings,
    )


def build_copilot_guidance_source(request: Request, session: AsyncSession) -> GuidancePort:
    services = build_signals_services(request, session)
    return SignalsGuidanceSource(guidance=services.guidance)
