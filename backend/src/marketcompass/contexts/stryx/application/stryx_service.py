"""The STRYX use case: hunt a setup, stream the call, and journal it.

Thin, but it owns the discipline that HELLA has no equivalent of:

1. *Before* the agent runs, it counts today's LIVE calls in the journal and, if
   the cap is already hit, tells the agent to answer NO TRADE / WATCHING only —
   the cap is enforced from the durable journal, never trusted to the model.
2. *After* the stream completes, it parses the answer into a structured call and
   appends it to the journal (every status, including NO TRADE), so STRYX's
   hit-rate can be backtested as its own metric later.

The agent loop, tools and model live behind ``AgentPort``; this use case only
sequences the discipline around it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from marketcompass.contexts.stryx.application.ports import (
    AgentDone,
    AgentEvent,
    AgentPort,
    TextDelta,
    TradeJournalPort,
    Turn,
)
from marketcompass.contexts.stryx.domain import call_template, discipline
from marketcompass.shared_kernel.types.identifiers import TenantId


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    symbol: str


def _source_of(answer: str) -> str:
    """Best-effort provenance for the journal: STRYX names mock data in its read."""
    lowered = answer.lower()
    return "mock" if ("mock" in lowered or "simulated" in lowered) else "live"


class StryxService:
    def __init__(self, *, agent: AgentPort, journal: TradeJournalPort) -> None:
        self._agent = agent
        self._journal = journal

    @property
    def available(self) -> bool:
        return self._agent.available

    async def stream(
        self,
        tenant_id: TenantId,
        symbol: str,
        question: str,
        history: list[Turn] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Stream STRYX's call, enforcing the cap up front and journaling at the end."""
        live_today = await self._journal.live_call_count_today(tenant_id)
        cap_reached = live_today >= discipline.MAX_LIVE_CALLS_PER_DAY

        parts: list[str] = []
        final = ""
        async for event in self._agent.run(
            tenant_id, symbol, question, history or [], cap_reached=cap_reached
        ):
            if isinstance(event, AgentDone):
                final = event.text
            elif isinstance(event, TextDelta):
                parts.append(event.text)
            yield event

        # Prefer the adapter's assembled final text; fall back to the streamed
        # deltas if it never sent a done event.
        answer = (final or "".join(parts)).strip()
        # Only journal actual calls — a friendly "hi, I'm STRYX" reply is not a
        # NO TRADE and must not fill the journal or touch the daily budget.
        if answer and call_template.is_call(answer):
            call = call_template.parse(answer)
            await self._journal.append(
                tenant_id,
                call,
                question=question,
                raw_answer=answer,
                source=_source_of(answer),
            )

    async def __call__(self, tenant_id: TenantId, symbol: str, question: str) -> Answer:
        """Collect the stream into one :class:`Answer` (non-streaming callers)."""
        parts: list[str] = []
        final = ""
        async for event in self.stream(tenant_id, symbol, question):
            if isinstance(event, AgentDone):
                final = event.text
            elif isinstance(event, TextDelta):
                parts.append(event.text)
        return Answer(text=(final or "".join(parts)).strip(), symbol=symbol)
