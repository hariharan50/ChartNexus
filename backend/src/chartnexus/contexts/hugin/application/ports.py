"""What the HUGIN context needs from the outside world.

Ports are ``typing.Protocol``s (structural, like STRYX), so the worker and the
read API share one code path and neither the loop nor the API imports an adapter.

* ``MemoryStorePort`` — the durable memory: append/grade observations, upsert and
  read lessons. Implemented by a repository that owns its own sessions, because
  the worker runs with no request scope.
* ``TenantDirectoryPort`` — enumerate enrolled tenants and their owner user, so a
  worker with no logged-in user can still know who to run for and whose LLM key to
  use (the owner's saved ``ai_settings`` key).
* ``ReflectorPort`` — the single LLM step that both judges last hour and produces
  this hour's read + lessons. Defined here; the LangGraph adapter lands in Phase 3.

Read DTOs (``MemoryView`` / ``ObservationView`` / ``LessonView``) keep the domain
aggregates from leaking to the API.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from chartnexus.contexts.hugin.domain.call import HuginCall
from chartnexus.contexts.hugin.domain.conversation import ChatEvent, Session, Turn
from chartnexus.contexts.hugin.domain.cycle import ReflectInput, ReflectOutput
from chartnexus.contexts.hugin.domain.lesson import Lesson
from chartnexus.contexts.hugin.domain.observation import Observation
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId

__all__ = [
    "CallGeneratorPort",
    "CallStorePort",
    "ChatPort",
    "DayView",
    "EnrolledTenant",
    "EnrollmentStorePort",
    "HistoryView",
    "LessonView",
    "MarketReaderPort",
    "MemoryStorePort",
    "MemoryView",
    "ObservationView",
    "ReflectInput",
    "ReflectOutput",
    "ReflectorPort",
    "SessionStorePort",
    "TenantDirectoryPort",
]


# --------------------------------------------------------------------------- #
# Read DTOs — what the API/UI sees. The domain aggregate never leaves here.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ObservationView:
    tick_at: datetime
    trading_day: date
    instrument: str
    bias: str
    expectation: str
    call_wall: Decimal | None
    put_wall: Decimal | None
    key_level: Decimal | None
    grade: str | None
    score: Decimal | None
    grade_evidence: dict[str, Any] | None

    @classmethod
    def of(cls, obs: Observation) -> ObservationView:
        return cls(
            tick_at=obs.tick_at,
            trading_day=obs.trading_day,
            instrument=obs.instrument,
            bias=obs.bias.value,
            expectation=obs.expectation,
            call_wall=obs.call_wall,
            put_wall=obs.put_wall,
            key_level=obs.key_level,
            grade=obs.grade.value if obs.grade is not None else None,
            score=obs.score,
            grade_evidence=obs.grade_evidence,
        )


@dataclass(frozen=True, slots=True)
class LessonView:
    text: str
    instrument: str | None
    hits: int
    misses: int
    reliability: float
    last_seen_at: datetime | None

    @classmethod
    def of(cls, lesson: Lesson) -> LessonView:
        return cls(
            text=lesson.text,
            instrument=lesson.instrument,
            hits=lesson.hits,
            misses=lesson.misses,
            reliability=lesson.reliability,
            last_seen_at=lesson.last_seen_at,
        )


@dataclass(frozen=True, slots=True)
class MemoryView:
    """Today's read model for one instrument: the timeline, lessons, and score."""

    instrument: str
    observations: tuple[ObservationView, ...]
    lessons: tuple[LessonView, ...]
    #: Fraction of *graded* observations today that scored HIT, or ``None`` when
    #: nothing has been graded yet (the scoreboard shows "—").
    hit_rate: float | None
    graded_count: int
    hit_count: int


@dataclass(frozen=True, slots=True)
class DayView:
    """One past trading day's reads and how well they scored — the sharpening unit."""

    trading_day: date
    observations: tuple[ObservationView, ...]
    hit_rate: float | None
    graded_count: int
    hit_count: int


@dataclass(frozen=True, slots=True)
class HistoryView:
    """HUGIN's track record across days for one instrument — newest day first."""

    instrument: str
    days: tuple[DayView, ...]
    #: Hit-rate across every graded read in the window (the headline track record).
    overall_hit_rate: float | None
    overall_graded: int
    overall_hits: int


# --------------------------------------------------------------------------- #
# Ports
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class EnrolledTenant:
    """A tenant the worker should run for, and the user whose LLM key it uses."""

    tenant_id: TenantId
    owner_user_id: UserId


class EnrollmentStorePort(Protocol):
    async def is_enabled(self, tenant_id: TenantId) -> bool:
        """Whether this tenant has opted HUGIN on. Absent row = off (the default)."""
        ...

    async def set_enabled(self, tenant_id: TenantId, enabled: bool) -> None:
        """Turn HUGIN on or off for this tenant, durably."""
        ...


class ChatPort(Protocol):
    @property
    def available(self) -> bool:
        """True when a model is configured — otherwise the chat is disabled."""
        ...

    def stream(self, digest: str, question: str, history: list[Turn]) -> AsyncIterator[ChatEvent]:
        """Answer ``question`` grounded in ``digest``, streaming text deltas."""
        ...


class SessionStorePort(Protocol):
    async def load(self, session_id: str | None) -> Session:
        """Fetch a session by id, or a fresh empty one when id is absent/expired."""
        ...

    async def save(self, session: Session) -> None:
        """Persist the session under a short TTL."""
        ...


class CallGeneratorPort(Protocol):
    @property
    def available(self) -> bool:
        """True when a model is configured — otherwise no call can be generated."""
        ...

    async def generate(
        self, digest: str, instrument: str, track_hit_rate: Decimal | None
    ) -> HuginCall:
        """Produce a memory-driven call grounded in ``digest``."""
        ...


class CallStorePort(Protocol):
    async def append(self, tenant_id: TenantId, call: HuginCall) -> None:
        """Persist a generated call."""
        ...

    async def recent(
        self, tenant_id: TenantId, instrument: str, limit: int
    ) -> tuple[HuginCall, ...]:
        """The most recent calls for this tenant x instrument, newest first."""
        ...


class MarketReaderPort(Protocol):
    async def snapshot(self, tenant_id: TenantId, instrument: str) -> dict[str, Any]:
        """The read-only market snapshot for one tenant x instrument."""
        ...


class ReflectorPort(Protocol):
    @property
    def available(self) -> bool:
        """True when a model is configured for the run — otherwise the tick is skipped."""
        ...

    async def reflect(self, request: ReflectInput) -> ReflectOutput:
        """Judge the prior read and produce this hour's read + lessons in one call."""
        ...


class TenantDirectoryPort(Protocol):
    async def enrolled_tenants(self) -> tuple[EnrolledTenant, ...]:
        """Active tenants to run for, each paired with its owner user."""
        ...


class MemoryStorePort(Protocol):
    async def latest_observation(self, tenant_id: TenantId, instrument: str) -> Observation | None:
        """The most recent observation for this tenant x instrument, if any."""
        ...

    async def append_observation(self, observation: Observation) -> None:
        """Persist a new (ungraded) observation."""
        ...

    async def grade_previous(
        self,
        observation_id: UUID,
        *,
        grade: str,
        score: Decimal,
        evidence: dict[str, Any],
    ) -> None:
        """Write a grade (and its cited evidence) onto a previously stored row."""
        ...

    async def lessons_for(
        self, tenant_id: TenantId, instrument: str, top_k: int
    ) -> tuple[Lesson, ...]:
        """The top-K lessons by reliability fed back into the reflect prompt."""
        ...

    async def upsert_lessons(self, tenant_id: TenantId, lessons: tuple[Lesson, ...]) -> None:
        """Insert new lessons or fold repeats onto their ``dedup_key``."""
        ...

    async def today(self, tenant_id: TenantId, instrument: str) -> tuple[Observation, ...]:
        """Every observation for this tenant x instrument on today's IST session."""
        ...

    async def history(
        self, tenant_id: TenantId, instrument: str, days: int
    ) -> tuple[Observation, ...]:
        """Observations across the last ``days`` IST trading days, oldest first."""
        ...

    async def all_lessons(self, tenant_id: TenantId) -> tuple[Lesson, ...]:
        """Every lesson this tenant has accumulated, across days and instruments."""
        ...
