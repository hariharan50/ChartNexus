"""Read use case behind the HUGIN tab.

Assembles the read model the API/UI polls: today's observations with their grades,
the active lessons, and the running hourly hit-rate HUGIN measures on itself. All
reads go through ``MemoryStorePort``; this use case owns no I/O of its own, so it
is trivially testable against a fake store.
"""

from __future__ import annotations

from chartnexus.contexts.hugin.application.ports import (
    LessonView,
    MemoryStorePort,
    MemoryView,
    ObservationView,
)
from chartnexus.contexts.hugin.domain.observation import Grade
from chartnexus.shared_kernel.types.identifiers import TenantId


class GetHuginMemory:
    """Reads HUGIN's durable memory for one tenant."""

    def __init__(self, store: MemoryStorePort, *, lessons_top_k: int) -> None:
        self._store = store
        self._lessons_top_k = lessons_top_k

    async def today(self, tenant_id: TenantId, instrument: str) -> MemoryView:
        observations = await self._store.today(tenant_id, instrument)
        lessons = await self._store.lessons_for(tenant_id, instrument, self._lessons_top_k)

        graded = [o for o in observations if o.grade is not None]
        hit_count = sum(1 for o in graded if o.grade is Grade.HIT)
        hit_rate = (hit_count / len(graded)) if graded else None

        return MemoryView(
            instrument=instrument,
            observations=tuple(ObservationView.of(o) for o in observations),
            lessons=tuple(LessonView.of(lsn) for lsn in lessons),
            hit_rate=hit_rate,
            graded_count=len(graded),
            hit_count=hit_count,
        )

    async def latest(self, tenant_id: TenantId, instrument: str) -> ObservationView | None:
        observation = await self._store.latest_observation(tenant_id, instrument)
        return ObservationView.of(observation) if observation is not None else None

    async def lessons(self, tenant_id: TenantId) -> tuple[LessonView, ...]:
        lessons = await self._store.all_lessons(tenant_id)
        return tuple(LessonView.of(lsn) for lsn in lessons)
