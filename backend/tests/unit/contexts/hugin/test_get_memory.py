"""GetHuginMemory read model — hit-rate and view assembly over a fake store."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from marketcompass.contexts.hugin.application.get_memory import GetHuginMemory
from marketcompass.contexts.hugin.domain.lesson import Lesson
from marketcompass.contexts.hugin.domain.observation import Bias, Grade, Observation
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())


def _obs(grade: Grade | None) -> Observation:
    return Observation(
        tenant_id=TENANT,
        instrument="NIFTY",
        tick_at=datetime.now(UTC),
        trading_day=datetime.now(UTC).date(),
        readings={},
        bias=Bias.BULLISH,
        expectation="holds above 23500",
        grade=grade,
    )


class _FakeStore:
    def __init__(self, observations: list[Observation], lessons: list[Lesson]) -> None:
        self._observations = observations
        self._lessons = lessons

    async def today(self, tenant_id: TenantId, instrument: str) -> tuple[Observation, ...]:
        return tuple(self._observations)

    async def lessons_for(
        self, tenant_id: TenantId, instrument: str, top_k: int
    ) -> tuple[Lesson, ...]:
        return tuple(self._lessons[:top_k])

    async def all_lessons(self, tenant_id: TenantId) -> tuple[Lesson, ...]:
        return tuple(self._lessons)

    # Unused by the read use case but part of the port.
    async def latest_observation(self, tenant_id, instrument):  # type: ignore[no-untyped-def]
        return self._observations[-1] if self._observations else None

    async def append_observation(self, observation):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def grade_previous(self, observation_id, *, grade, score, evidence):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def upsert_lessons(self, tenant_id, lessons):  # type: ignore[no-untyped-def]
        raise NotImplementedError


async def test_hit_rate_counts_only_graded_reads() -> None:
    store = _FakeStore(
        observations=[_obs(Grade.HIT), _obs(Grade.MISS), _obs(None)],
        lessons=[],
    )
    view = await GetHuginMemory(store, lessons_top_k=8).today(TENANT, "NIFTY")

    assert view.graded_count == 2
    assert view.hit_count == 1
    assert view.hit_rate == 0.5
    assert len(view.observations) == 3


async def test_hit_rate_is_none_when_nothing_graded() -> None:
    store = _FakeStore(observations=[_obs(None)], lessons=[])
    view = await GetHuginMemory(store, lessons_top_k=8).today(TENANT, "NIFTY")

    assert view.graded_count == 0
    assert view.hit_rate is None


async def test_lessons_view_carries_reliability() -> None:
    store = _FakeStore(
        observations=[],
        lessons=[Lesson(dedup_key="pcr_flip", text="PCR flip leads", hits=3, misses=1)],
    )
    view = await GetHuginMemory(store, lessons_top_k=8).today(TENANT, "NIFTY")

    assert view.lessons[0].hits == 3
    assert 0.0 < view.lessons[0].reliability < 1.0
