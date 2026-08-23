"""HUGIN reflector mapping — structured LLM output to domain, with a fake model.

No network: a fake chat model returns a fixed ``_ReflectSchema`` so the mapping
(grade gating, Decimal walls, confirmed/refuted lesson accrual, unknown-key
ignore) is pinned without an API key.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from marketcompass.contexts.hugin.domain.cycle import ReflectInput
from marketcompass.contexts.hugin.domain.lesson import Lesson
from marketcompass.contexts.hugin.domain.observation import Bias, Grade, Observation
from marketcompass.infrastructure.agent.langgraph import hugin_reflector as hr
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())


class _Runnable:
    def __init__(self, out: hr._ReflectSchema) -> None:
        self._out = out

    async def ainvoke(self, messages: object) -> hr._ReflectSchema:
        return self._out


class _FakeModel:
    def __init__(self, out: hr._ReflectSchema) -> None:
        self._out = out

    def with_structured_output(self, schema: object) -> _Runnable:
        return _Runnable(self._out)


def _schema(*, with_grade: bool) -> hr._ReflectSchema:
    return hr._ReflectSchema(
        bias="BULLISH",
        expectation="holds above 23500, tags 23620",
        call_wall=23600,
        put_wall=23400,
        key_level=23500,
        new_lessons=[hr._NewLesson(dedup_key="vwap_reclaim", text="VWAP reclaim precedes the leg")],
        confirmed_lessons=["pcr_flip", "ghost"],  # 'ghost' is unknown -> ignored
        refuted_lessons=["ema_cross"],
        prior_grade=(
            hr._PriorGrade(
                grade="HIT",
                score=0.82,
                evidence=hr._Evidence(
                    expected_move="up to 23600",
                    actual_move="tagged 23615",
                    wall_status="held",
                    level_status="respected",
                ),
            )
            if with_grade
            else None
        ),
    )


def _prior() -> Observation:
    return Observation(
        tenant_id=TENANT,
        instrument="NIFTY",
        tick_at=datetime.now(UTC),
        trading_day=datetime.now(UTC).date(),
        readings={},
        bias=Bias.NEUTRAL,
        expectation="range 23400-23600",
        id=uuid.uuid4(),
    )


_EXISTING = (
    Lesson(dedup_key="pcr_flip", text="PCR flip leads reversals", instrument="NIFTY", hits=2),
    Lesson(dedup_key="ema_cross", text="EMA cross lags in chop", instrument="NIFTY"),
)


async def test_maps_grade_and_walls_when_a_prior_exists() -> None:
    reflector = hr.HuginReflector(_FakeModel(_schema(with_grade=True)))
    out = await reflector.reflect(
        ReflectInput(
            instrument="NIFTY", snapshot={"get_spot": "23615"}, prior=_prior(), lessons=_EXISTING
        )
    )

    assert out.bias is Bias.BULLISH
    assert out.call_wall == Decimal("23600")
    assert out.prior_grade is not None
    assert out.prior_grade.grade is Grade.HIT
    assert out.prior_grade.score == Decimal("0.82")
    assert out.prior_grade.evidence["actual_move"] == "tagged 23615"


async def test_confirmed_and_refuted_lessons_accrue_and_unknown_keys_are_ignored() -> None:
    reflector = hr.HuginReflector(_FakeModel(_schema(with_grade=True)))
    out = await reflector.reflect(
        ReflectInput(instrument="NIFTY", snapshot={}, prior=_prior(), lessons=_EXISTING)
    )

    by_key = {(lesson.dedup_key, lesson.hits, lesson.misses) for lesson in out.lessons}
    assert ("vwap_reclaim", 0, 0) in by_key  # new lesson, neutral
    assert ("pcr_flip", 1, 0) in by_key  # confirmed -> +hit
    assert ("ema_cross", 0, 1) in by_key  # refuted -> +miss
    assert not any(key == "ghost" for key, _, _ in by_key)  # unknown ignored


async def test_grade_is_dropped_when_there_is_no_prior() -> None:
    reflector = hr.HuginReflector(_FakeModel(_schema(with_grade=True)))
    out = await reflector.reflect(
        ReflectInput(instrument="NIFTY", snapshot={}, prior=None, lessons=())
    )
    assert out.prior_grade is None
