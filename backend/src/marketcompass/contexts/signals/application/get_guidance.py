"""Fetch a snapshot, run the pure pipeline, persist the call when it moves.

The whole judgement lives in ``domain.guider.build_guidance``; this use case only
adds the two things a pure function cannot do — read the market through a port
and write the result — plus the dedup rule that turns a 15-second poll into a
readable history of *changes* rather than hundreds of identical rows.
"""

from __future__ import annotations

from marketcompass.contexts.signals.application.ports import (
    GuidanceRepositoryPort,
    MarketReadPort,
)
from marketcompass.contexts.signals.domain.guider import build_guidance
from marketcompass.contexts.signals.domain.models import Guidance
from marketcompass.shared_kernel.types.identifiers import TenantId

# A decision is re-persisted when the call flips or conviction moves more than
# this many points — enough to log a genuine shift, not every poll's jitter.
_CONFIDENCE_STEP = 10


class GetGuidance:
    def __init__(self, *, market: MarketReadPort, repository: GuidanceRepositoryPort) -> None:
        self._market = market
        self._repository = repository

    async def __call__(self, tenant_id: TenantId, symbol: str) -> Guidance:
        snapshot = await self._market.read(tenant_id, symbol)
        guidance = build_guidance(snapshot)
        await self._persist_if_changed(tenant_id, guidance)
        return guidance

    async def _persist_if_changed(self, tenant_id: TenantId, guidance: Guidance) -> None:
        last = await self._repository.latest(tenant_id, guidance.symbol)
        unchanged = (
            last is not None
            and last.decision is guidance.decision
            and abs(last.confidence - guidance.confidence) < _CONFIDENCE_STEP
        )
        if unchanged:
            return
        await self._repository.save(tenant_id, guidance)
