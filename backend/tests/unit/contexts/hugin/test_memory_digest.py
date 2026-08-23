"""The memory digest — HUGIN's only source of truth for chat/calls."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from marketcompass.contexts.hugin.domain.lesson import Lesson
from marketcompass.contexts.hugin.domain.memory_digest import build_digest, is_empty
from marketcompass.contexts.hugin.domain.observation import Bias, Grade, Observation
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())


def _obs(grade: Grade | None) -> Observation:
    return Observation(
        tenant_id=TENANT,
        instrument="NIFTY",
        tick_at=datetime(2026, 8, 24, 10, 15, tzinfo=UTC),
        trading_day=datetime(2026, 8, 24, tzinfo=UTC).date(),
        readings={},
        bias=Bias.BULLISH,
        expectation="hold above 23500",
        grade=grade,
    )


def test_digest_includes_reads_lessons_and_rates() -> None:
    digest = build_digest(
        instrument="NIFTY",
        today=(_obs(Grade.HIT),),
        lessons=(Lesson(dedup_key="pcr_flip", text="PCR flip leads", hits=3, misses=1),),
        hit_rate_today=0.75,
        overall_hit_rate=0.6,
    )
    assert "HUGIN MEMORY — NIFTY" in digest
    assert "hold above 23500" in digest
    assert "PCR flip leads" in digest
    assert "75%" in digest and "60%" in digest


def test_digest_marks_empty_memory() -> None:
    digest = build_digest(
        instrument="NIFTY",
        today=(),
        lessons=(),
        hit_rate_today=None,
        overall_hit_rate=None,
    )
    assert "(none yet today)" in digest
    assert "n/a" in digest
    assert is_empty((), ()) is True
    assert is_empty((_obs(None),), ()) is False
