"""The MME100 chat use case: analyse and stream.

Thinner than STRYX's — MME100 keeps no journal and enforces no cap. It simply
sequences the agent's stream and assembles the final answer for non-streaming
callers. The agent loop, tools, web search and model live behind ``AgentPort``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from chartnexus.contexts.mme100.application.ports import (
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


class Mme100Service:
    def __init__(self, *, agent: AgentPort) -> None:
        self._agent = agent

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
        """Stream MME100's analysis for ``symbol``."""
        async for event in self._agent.run(tenant_id, symbol, question, history or []):
            yield event

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
