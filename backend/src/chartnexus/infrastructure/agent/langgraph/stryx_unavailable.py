"""STRYX when no model is configured — import-safe without the 'agent' extra.

``StryxLangGraphAgent`` imports LangChain at module load, so when the optional
``agent`` extra isn't installed importing it raises ``ImportError``. The STRYX
dependency must still answer ``/stryx/availability`` in that state, so when there
is no model the builder returns *this* instead — a trivial ``AgentPort`` that
reports unavailable and imports nothing heavy.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from chartnexus.contexts.stryx.application.ports import AgentEvent, Turn
from chartnexus.shared_kernel.types.identifiers import TenantId


class UnavailableStryxAgent:
    """An ``AgentPort`` that is never available. The tab is disabled upstream."""

    available = False

    async def run(
        self,
        tenant_id: TenantId,
        symbol: str,
        question: str,
        history: list[Turn],
        *,
        cap_reached: bool,
    ) -> AsyncIterator[AgentEvent]:
        # Never invoked in practice — the transport gates on ``available`` and
        # returns 503 first. An empty async generator rather than a raise, so a
        # stray call degrades to "no answer" not a crash.
        _ = (tenant_id, symbol, question, history, cap_reached)
        empty: tuple[AgentEvent, ...] = ()
        for event in empty:  # pragma: no cover
            yield event
