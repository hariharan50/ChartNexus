"""Fetch a snapshot, run the calibrated engine, persist the call when it moves.

The judgement lives in ``domain.guider.build_multi_horizon``; this use case adds
the two things a pure function cannot do — read the market through a port and
supply the fitted model — plus the dedup rule that turns a 15-second poll into a
readable history of *changes* (tracked on the intraday headline).
"""

from __future__ import annotations

from marketcompass.contexts.signals.application.ports import (
    GuidanceRepositoryPort,
    MarketReadPort,
    ModelPort,
)
from marketcompass.contexts.signals.domain.guider import build_multi_horizon
from marketcompass.contexts.signals.domain.models import (
    Decision,
    Guidance,
    Levels,
    MultiHorizonGuidance,
)
from marketcompass.shared_kernel.types.identifiers import TenantId

# A decision is re-persisted when the headline call flips or conviction moves more
# than this many points — enough to log a genuine shift, not every poll's jitter.
_CONFIDENCE_STEP = 10


class GetGuidance:
    def __init__(
        self,
        *,
        market: MarketReadPort,
        repository: GuidanceRepositoryPort,
        model: ModelPort,
    ) -> None:
        self._market = market
        self._repository = repository
        self._model = model

    async def __call__(self, tenant_id: TenantId, symbol: str) -> MultiHorizonGuidance:
        snapshot = await self._market.read(tenant_id, symbol)
        guidance = build_multi_horizon(snapshot, self._model.artifact())
        await self._persist_if_changed(tenant_id, guidance)
        return guidance

    async def _persist_if_changed(
        self, tenant_id: TenantId, guidance: MultiHorizonGuidance
    ) -> None:
        headline = guidance.headline
        if headline is None:
            return
        last = await self._repository.latest(tenant_id, guidance.symbol)
        unchanged = (
            last is not None
            and last.decision is headline.decision
            and abs(last.confidence - headline.confidence) < _CONFIDENCE_STEP
        )
        if unchanged:
            return
        await self._repository.save(tenant_id, _headline_guidance(guidance, headline.decision))


def _headline_guidance(guidance: MultiHorizonGuidance, decision: Decision) -> Guidance:
    """A thin ``Guidance`` carrying the headline, for the change-history record.

    Only the fields the repository persists (decision/confidence/score/provenance/
    symbol) are meaningful; the rest are filled minimally.
    """
    headline = guidance.headline
    confidence = headline.confidence if headline else 0
    # Score in [-1, +1] from the intraday probability, for the history strip.
    score = round((headline.probability - 0.5) * 2.0, 4) if headline else 0.0
    return Guidance(
        symbol=guidance.symbol,
        decision=decision,
        confidence=confidence,
        score=score,
        provenance=guidance.provenance,
        skills=(),
        levels=guidance.levels if guidance.levels else Levels(spot=0.0),
        scaffold=guidance.scaffold,
        rationale=guidance.rationale,
        expiry_ref=guidance.expiry_ref,
        is_actionable=guidance.is_actionable,
        warnings=guidance.warnings,
    )
