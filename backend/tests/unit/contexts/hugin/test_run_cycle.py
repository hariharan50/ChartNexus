"""RunHuginCycle sequencing — persist, grade-next-tick, skip, and survive."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from chartnexus.contexts.hugin.application.run_cycle import RunHuginCycle
from chartnexus.contexts.hugin.domain.cycle import CycleStatus, ReflectInput, ReflectOutput
from chartnexus.contexts.hugin.domain.grade import GradeOutcome
from chartnexus.contexts.hugin.domain.lesson import Lesson
from chartnexus.contexts.hugin.domain.observation import Bias, Grade, Observation
from chartnexus.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())


class _FakeStore:
    def __init__(self) -> None:
        self.observations: list[Observation] = []
        self.graded: list[tuple] = []
        self.upserted: list[Lesson] = []

    async def latest_observation(self, tenant_id, instrument):  # type: ignore[no-untyped-def]
        rows = [o for o in self.observations if o.instrument == instrument]
        return rows[-1] if rows else None

    async def append_observation(self, observation: Observation) -> None:
        object.__setattr__(observation, "id", uuid.uuid4())
        self.observations.append(observation)

    async def grade_previous(self, observation_id, *, grade, score, evidence):  # type: ignore[no-untyped-def]
        self.graded.append((observation_id, grade, score, evidence))

    async def lessons_for(self, tenant_id, instrument, top_k):  # type: ignore[no-untyped-def]
        return ()

    async def upsert_lessons(self, tenant_id, lessons):  # type: ignore[no-untyped-def]
        self.upserted.extend(lessons)

    async def today(self, tenant_id, instrument):  # type: ignore[no-untyped-def]
        return tuple(self.observations)

    async def all_lessons(self, tenant_id):  # type: ignore[no-untyped-def]
        return ()


class _FakeMarket:
    async def snapshot(self, tenant_id, instrument):  # type: ignore[no-untyped-def]
        return {"get_spot": f"{instrument} spot 23500"}


class _FakeReflector:
    available = True

    def __init__(self, *, grade_prior: bool) -> None:
        self._grade_prior = grade_prior

    async def reflect(self, request: ReflectInput) -> ReflectOutput:
        prior_grade = None
        if self._grade_prior and request.prior is not None:
            prior_grade = GradeOutcome(
                grade=Grade.HIT, score=Decimal("0.8"), evidence={"actual_move": "+50"}
            )
        return ReflectOutput(
            bias=Bias.BULLISH,
            expectation="holds above 23500",
            call_wall=Decimal("23600"),
            put_wall=None,
            key_level=None,
            lessons=(Lesson(dedup_key="k", text="a lesson", instrument=request.instrument),),
            prior_grade=prior_grade,
        )


class _Unavailable:
    available = False

    async def reflect(self, request):  # type: ignore[no-untyped-def]
        raise AssertionError("must not be called when unavailable")


class _Boom:
    available = True

    async def reflect(self, request):  # type: ignore[no-untyped-def]
        raise RuntimeError("model blew up")


def _cycle(store, reflector) -> RunHuginCycle:  # type: ignore[no-untyped-def]
    return RunHuginCycle(market=_FakeMarket(), reflector=reflector, store=store, lessons_top_k=8)


async def test_first_cycle_persists_without_grading() -> None:
    store = _FakeStore()
    result = await _cycle(store, _FakeReflector(grade_prior=True))(
        TENANT, "NIFTY", tick_at=datetime.now(UTC)
    )
    assert result.status is CycleStatus.PERSISTED
    assert result.graded_prior is False
    assert len(store.observations) == 1
    assert store.graded == []


async def test_second_cycle_grades_the_prior_observation() -> None:
    store = _FakeStore()
    cycle = _cycle(store, _FakeReflector(grade_prior=True))
    now = datetime.now(UTC)
    await cycle(TENANT, "NIFTY", tick_at=now)
    result = await cycle(TENANT, "NIFTY", tick_at=now)

    assert result.graded_prior is True
    assert len(store.graded) == 1
    assert store.graded[0][1] == "HIT"


async def test_unavailable_reflector_skips_the_cycle() -> None:
    store = _FakeStore()
    result = await _cycle(store, _Unavailable())(TENANT, "NIFTY", tick_at=datetime.now(UTC))
    assert result.status is CycleStatus.SKIPPED_UNAVAILABLE
    assert store.observations == []


async def test_a_failing_reflect_is_swallowed_as_failed() -> None:
    store = _FakeStore()
    result = await _cycle(store, _Boom())(TENANT, "NIFTY", tick_at=datetime.now(UTC))
    assert result.status is CycleStatus.FAILED
    assert store.observations == []
