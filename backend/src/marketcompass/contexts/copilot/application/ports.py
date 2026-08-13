"""What the copilot context needs from the outside world.

* ``AgentPort`` — the agentic guider (Hella). It runs a tool-calling loop over
  read-only market-data tools and streams :class:`AgentEvent`s. ``available``
  gates the whole feature: the console is LLM-only, so with no model configured
  the tab is disabled rather than degraded. Satisfied by a LangGraph adapter in
  ``infrastructure/agent``.
* ``SessionStorePort`` — short-lived, server-side conversation memory, so
  follow-up questions carry context within a session (no long-term persistence).

The agent value objects (``Turn``, the ``AgentEvent`` union, ``Session``) live in
``domain.agent`` and are re-exported here so callers import them from one place.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from marketcompass.contexts.copilot.domain.agent import (
    AgentDone,
    AgentEvent,
    Session,
    SkillsSelected,
    TextDelta,
    ToolFinished,
    ToolStarted,
    Turn,
)
from marketcompass.shared_kernel.types.identifiers import TenantId

__all__ = [
    "AgentDone",
    "AgentEvent",
    "AgentPort",
    "Session",
    "SessionStorePort",
    "SkillsSelected",
    "TextDelta",
    "ToolFinished",
    "ToolStarted",
    "Turn",
]


class AgentPort(Protocol):
    @property
    def available(self) -> bool:
        """True when a model is configured and the agent can answer.

        False disables the console tab — there is no keyless degradation.
        """
        ...

    def run(
        self,
        tenant_id: TenantId,
        symbol: str,
        question: str,
        history: list[Turn],
    ) -> AsyncIterator[AgentEvent]:
        """Answer ``question`` about ``symbol``, streaming :class:`AgentEvent`s.

        ``history`` is the prior conversation (oldest first, excluding this
        question). The adapter owns the tool-calling loop and its tools.
        """
        ...


class SessionStorePort(Protocol):
    async def load(self, session_id: str | None) -> Session:
        """Fetch a session by id, or a fresh empty one when id is absent/expired."""
        ...

    async def save(self, session: Session) -> None:
        """Persist the session under a short TTL."""
        ...
