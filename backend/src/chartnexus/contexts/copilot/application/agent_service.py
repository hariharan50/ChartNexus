"""The AI Console use case: stream Hella's answer, and collect it when needed.

Thin by design. The agent loop, tools and model all live behind ``AgentPort``
(a LangGraph adapter); this use case only chooses between streaming and
collecting, and reports whether the agent is available at all.

There is no keyless path: the console is LLM-only. When ``available`` is False
the transport disables the tab rather than degrading to a canned answer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from chartnexus.contexts.copilot.application.ports import (
    AgentDone,
    AgentEvent,
    AgentPort,
    TextDelta,
    Turn,
)
from chartnexus.shared_kernel.types.identifiers import TenantId


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    symbol: str


class AgentService:
    def __init__(self, *, agent: AgentPort) -> None:
        self._agent = agent

    @property
    def available(self) -> bool:
        return self._agent.available

    def stream(
        self,
        tenant_id: TenantId,
        symbol: str,
        question: str,
        history: list[Turn] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        return self._agent.run(tenant_id, symbol, question, history or [])

    async def __call__(self, tenant_id: TenantId, symbol: str, question: str) -> Answer:
        """Collect the stream into one :class:`Answer` (non-streaming callers)."""
        parts: list[str] = []
        async for event in self.stream(tenant_id, symbol, question):
            if isinstance(event, TextDelta):
                parts.append(event.text)
            elif isinstance(event, AgentDone):
                parts = [event.text]
        return Answer(text="".join(parts).strip(), symbol=symbol)
