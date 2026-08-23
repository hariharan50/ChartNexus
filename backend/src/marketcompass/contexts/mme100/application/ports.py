"""What the MME100 context needs from the outside world.

* ``AgentPort`` — the tool-calling analyst. Streams :class:`AgentEvent`s.
  ``available`` gates the whole feature: MME100 is LLM-only, so with no model the
  tab is disabled rather than degraded. Satisfied by a LangGraph adapter in
  ``infrastructure/agent``.
* ``SessionStorePort`` — short-lived, server-side conversation memory (its own
  Redis namespace, separate from HELLA's and STRYX's).
* ``BriefingStorePort`` — the durable daily pre-market briefing the worker writes
  and the API reads back. Implemented by a repository that owns its own sessions,
  because the worker runs with no request scope.
* ``EnrollmentStorePort`` — the per-tenant opt-in for the autonomous briefing.
* ``TenantDirectoryPort`` — enumerate enrolled tenants and their owner user, so a
  worker with no logged-in user knows who to run for and whose LLM key to use.

The agent value objects live in ``domain.agent`` and are re-exported here so
callers import the whole vocabulary from one place.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from marketcompass.contexts.mme100.domain.agent import (
    AgentDone,
    AgentEvent,
    Session,
    SkillsConsidered,
    TextDelta,
    ToolFinished,
    ToolStarted,
    Turn,
)
from marketcompass.contexts.mme100.domain.briefing import Briefing
from marketcompass.shared_kernel.types.identifiers import TenantId, UserId

__all__ = [
    "AgentDone",
    "AgentEvent",
    "AgentPort",
    "Briefing",
    "BriefingStorePort",
    "EnrolledTenant",
    "EnrollmentStorePort",
    "Session",
    "SessionStorePort",
    "SkillsConsidered",
    "TenantDirectoryPort",
    "TextDelta",
    "ToolFinished",
    "ToolStarted",
    "Turn",
]


class AgentPort(Protocol):
    @property
    def available(self) -> bool:
        """True when a model is configured and MME100 can answer.

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
        """Analyse ``symbol`` (or answer small talk), streaming :class:`AgentEvent`s.

        The adapter owns the tool loop, the web search, and the analysis/
        conversation routing.
        """
        ...


class SessionStorePort(Protocol):
    async def load(self, session_id: str | None) -> Session:
        """Fetch a session by id, or a fresh empty one when id is absent/expired."""
        ...

    async def save(self, session: Session) -> None:
        """Persist the session under a short TTL."""
        ...


class BriefingStorePort(Protocol):
    async def save(self, tenant_id: TenantId, briefing: Briefing) -> None:
        """Persist (or replace) a tenant's briefing for its trading day."""
        ...

    async def today(self, tenant_id: TenantId) -> Briefing | None:
        """The tenant's briefing for today's IST trading day, if one exists."""
        ...


class EnrollmentStorePort(Protocol):
    async def is_enabled(self, tenant_id: TenantId) -> bool:
        """Whether this tenant has opted the pre-market briefing on. Absent row = off."""
        ...

    async def set_enabled(self, tenant_id: TenantId, enabled: bool) -> None:
        """Turn the briefing on or off for this tenant, durably."""
        ...


@dataclass(frozen=True, slots=True)
class EnrolledTenant:
    """A tenant the worker should run for, and the user whose LLM key it uses."""

    tenant_id: TenantId
    owner_user_id: UserId


class TenantDirectoryPort(Protocol):
    async def enrolled_tenants(self) -> tuple[EnrolledTenant, ...]:
        """Active tenants to run the briefing for, each paired with its owner user."""
        ...
