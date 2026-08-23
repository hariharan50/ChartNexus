"""RunMme100Briefing — one tenant's autonomous pre-market briefing.

Each trading morning the worker runs this once per enrolled tenant: for every
configured instrument it asks the analyst for the full six-section read, stitches
the answers into one markdown document, and persists it as today's briefing.

Stateless per call and **swallow-and-survive**: any failure is logged and returns
``None``, never raised, so one bad tenant can't kill the worker's run (the same
rule the HUGIN cycle and the ingest loop follow).
"""

from __future__ import annotations

import logging
from datetime import datetime

from marketcompass.contexts.mme100.application.ports import (
    AgentDone,
    AgentPort,
    BriefingStorePort,
    TextDelta,
)
from marketcompass.contexts.mme100.domain import persona
from marketcompass.contexts.mme100.domain.briefing import Briefing
from marketcompass.contexts.mme100.domain.schedule import to_ist
from marketcompass.shared_kernel.types.identifiers import TenantId

log = logging.getLogger(__name__)


def _source_of(markdown: str) -> str:
    """Best-effort provenance: the analyst names simulated data in its read."""
    lowered = markdown.lower()
    return "mock" if ("mock" in lowered or "simulated" in lowered) else "live"


class RunMme100Briefing:
    """Generates and stores one tenant's pre-market briefing for the trading day."""

    def __init__(
        self,
        *,
        agent: AgentPort,
        store: BriefingStorePort,
        instruments: tuple[str, ...],
    ) -> None:
        self._agent = agent
        self._store = store
        self._instruments = instruments

    async def __call__(self, tenant_id: TenantId, *, tick_at: datetime) -> Briefing | None:
        # No model, no briefing: analysis needs the LLM, so a tenant whose owner
        # has no key produces nothing (the tab reads as unavailable).
        if not self._agent.available:
            return None
        try:
            return await self._run(tenant_id, tick_at=tick_at)
        except Exception:
            log.exception("mme100 briefing failed for tenant=%s", tenant_id)
            return None

    async def _run(self, tenant_id: TenantId, *, tick_at: datetime) -> Briefing | None:
        sections: list[str] = []
        for instrument in self._instruments:
            markdown = await self._analyse(tenant_id, instrument)
            if markdown:
                sections.append(f"## {instrument}\n\n{markdown}")

        if not sections:
            return None

        full = "\n\n---\n\n".join(sections)
        briefing = Briefing(
            trading_day=to_ist(tick_at).date(),
            instruments=self._instruments,
            markdown=full,
            source=_source_of(full),
        )
        await self._store.save(tenant_id, briefing)
        return briefing

    async def _analyse(self, tenant_id: TenantId, instrument: str) -> str:
        parts: list[str] = []
        final = ""
        async for event in self._agent.run(
            tenant_id, instrument, persona.briefing_prompt(instrument), []
        ):
            if isinstance(event, AgentDone):
                final = event.text
            elif isinstance(event, TextDelta):
                parts.append(event.text)
        return (final or "".join(parts)).strip()
