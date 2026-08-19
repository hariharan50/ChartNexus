"""What the STRYX context needs from the outside world.

* ``AgentPort`` — the tool-calling operator. Streams :class:`AgentEvent`s.
  ``available`` gates the whole feature: STRYX is LLM-only, so with no model the
  tab is disabled rather than degraded. Satisfied by a LangGraph adapter in
  ``infrastructure/agent``.
* ``SessionStorePort`` — short-lived, server-side conversation memory (its own
  Redis namespace, separate from HELLA's).
* ``TradeJournalPort`` — the discipline spine: every call (LIVE / NO TRADE /
  WATCHING) is logged, and the day's LIVE count is what enforces the hard cap.

The agent value objects live in ``domain.agent`` and are re-exported here so
callers import the whole vocabulary from one place.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from marketcompass.contexts.stryx.domain.agent import (
    AgentDone,
    AgentEvent,
    Session,
    StylesConsidered,
    TextDelta,
    ToolFinished,
    ToolStarted,
    Turn,
)
from marketcompass.contexts.stryx.domain.call_template import StryxCall
from marketcompass.shared_kernel.types.identifiers import TenantId

__all__ = [
    "AgentDone",
    "AgentEvent",
    "AgentPort",
    "JournalEntry",
    "Session",
    "SessionStorePort",
    "StylesConsidered",
    "TextDelta",
    "ToolFinished",
    "ToolStarted",
    "TradeJournalPort",
    "Turn",
]


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """One journaled STRYX call, read back for the day's journal view."""

    created_at: datetime
    instrument: str | None
    entry_style: str | None
    status: str
    entry: str | None
    stop: str | None
    target1: str | None
    target2: str | None
    confidence: str | None
    reasoning: str | None


class AgentPort(Protocol):
    @property
    def available(self) -> bool:
        """True when a model is configured and STRYX can answer.

        False disables the console tab — there is no keyless degradation.
        """
        ...

    def run(
        self,
        tenant_id: TenantId,
        symbol: str,
        question: str,
        history: list[Turn],
        *,
        cap_reached: bool,
    ) -> AsyncIterator[AgentEvent]:
        """Hunt a setup on ``symbol``, streaming :class:`AgentEvent`s.

        ``cap_reached`` tells STRYX the day's LIVE-call cap is already hit, so it
        must answer NO TRADE / WATCHING only. The adapter owns the tool loop.
        """
        ...


class SessionStorePort(Protocol):
    async def load(self, session_id: str | None) -> Session:
        """Fetch a session by id, or a fresh empty one when id is absent/expired."""
        ...

    async def save(self, session: Session) -> None:
        """Persist the session under a short TTL."""
        ...


class TradeJournalPort(Protocol):
    async def append(
        self,
        tenant_id: TenantId,
        call: StryxCall,
        *,
        question: str,
        raw_answer: str,
        source: str,
    ) -> None:
        """Record a call (any status) for this tenant's trading day."""
        ...

    async def live_call_count_today(self, tenant_id: TenantId) -> int:
        """How many LIVE calls this tenant has been issued so far today (IST)."""
        ...

    async def today(self, tenant_id: TenantId) -> tuple[JournalEntry, ...]:
        """Every call logged for this tenant today (IST), newest first."""
        ...
