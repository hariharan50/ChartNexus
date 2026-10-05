"""HUGIN memory repository against real Postgres.

Covers the round-trip the unit tests cannot: an observation persists and reads
back, the next tick grades the prior row, "today" scopes to the IST session, and
lessons upsert additively on their dedup key.

Requires the compose stack:  docker compose -f deploy/compose/compose.yml up -d
and migrations applied:       uv run alembic upgrade head
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from chartnexus.bootstrap.settings import DatabaseSettings
from chartnexus.contexts.hugin.domain.lesson import Lesson
from chartnexus.contexts.hugin.domain.observation import Bias, Grade, Observation
from chartnexus.infrastructure.persistence.postgresql.repositories.hugin.memory_repository import (
    SqlAlchemyHuginMemoryRepository,
)
from chartnexus.infrastructure.persistence.postgresql.session import Database
from chartnexus.shared_kernel.types.identifiers import TenantId

pytestmark = pytest.mark.integration

ASYNC_DSN = "postgresql+asyncpg://chartnexus:chartnexus@localhost:5433/chartnexus"


@pytest.fixture
async def database() -> AsyncIterator[Database]:
    db = Database.create(DatabaseSettings(url=ASYNC_DSN), use_pool=False)  # type: ignore[arg-type]
    yield db
    await db.dispose()


def _obs(tenant: TenantId, expectation: str) -> Observation:
    now = datetime.now(UTC)
    return Observation(
        tenant_id=tenant,
        instrument="NIFTY",
        tick_at=now,
        trading_day=now.date(),
        readings={"get_spot": "NIFTY 23500"},
        bias=Bias.BULLISH,
        expectation=expectation,
        call_wall=Decimal("23600"),
        put_wall=Decimal("23400"),
        key_level=Decimal("23500"),
    )


async def test_observation_round_trip_and_grading(database: Database) -> None:
    repo = SqlAlchemyHuginMemoryRepository(database)
    tenant = TenantId(uuid.uuid4())

    await repo.append_observation(_obs(tenant, "holds above 23500"))

    latest = await repo.latest_observation(tenant, "NIFTY")
    assert latest is not None
    assert latest.expectation == "holds above 23500"
    assert latest.call_wall == Decimal("23600")
    assert latest.grade is None
    assert latest.id is not None

    await repo.grade_previous(
        latest.id, grade="HIT", score=Decimal("0.9"), evidence={"actual_move": "+60"}
    )

    today = await repo.today(tenant, "NIFTY")
    assert len(today) == 1
    assert today[0].grade is Grade.HIT
    assert today[0].score == Decimal("0.9")
    assert today[0].grade_evidence == {"actual_move": "+60"}


async def test_lessons_upsert_additively(database: Database) -> None:
    repo = SqlAlchemyHuginMemoryRepository(database)
    tenant = TenantId(uuid.uuid4())

    await repo.upsert_lessons(
        tenant, (Lesson(dedup_key="pcr_flip", text="PCR flip leads", instrument="NIFTY", hits=1),)
    )
    await repo.upsert_lessons(
        tenant,
        (
            Lesson(
                dedup_key="pcr_flip", text="PCR flip leads reversals", instrument="NIFTY", hits=1
            ),
        ),
    )

    lessons = await repo.all_lessons(tenant)
    pcr = [lesson for lesson in lessons if lesson.dedup_key == "pcr_flip"]
    assert len(pcr) == 1  # folded onto one row
    assert pcr[0].hits == 2  # deltas accrued
    assert pcr[0].text == "PCR flip leads reversals"  # text refreshed


async def test_history_returns_recent_days(database: Database) -> None:
    repo = SqlAlchemyHuginMemoryRepository(database)
    tenant = TenantId(uuid.uuid4())

    now = datetime.now(UTC)
    today = _obs(tenant, "today read")
    old = Observation(
        tenant_id=tenant,
        instrument="NIFTY",
        tick_at=now - timedelta(days=2),
        trading_day=(now - timedelta(days=2)).date(),
        readings={"get_spot": "old"},
        bias=Bias.NEUTRAL,
        expectation="two days ago",
    )
    await repo.append_observation(today)
    await repo.append_observation(old)

    within = await repo.history(tenant, "NIFTY", days=7)
    assert {o.expectation for o in within} == {"today read", "two days ago"}

    only_today = await repo.history(tenant, "NIFTY", days=1)
    assert {o.expectation for o in only_today} == {"today read"}


async def test_lessons_for_ranks_by_reliability(database: Database) -> None:
    repo = SqlAlchemyHuginMemoryRepository(database)
    tenant = TenantId(uuid.uuid4())

    await repo.upsert_lessons(
        tenant,
        (
            Lesson(dedup_key="weak", text="weak", instrument="NIFTY", misses=3),
            Lesson(dedup_key="strong", text="strong", instrument="NIFTY", hits=5),
        ),
    )
    ranked = await repo.lessons_for(tenant, "NIFTY", top_k=1)
    assert len(ranked) == 1
    assert ranked[0].dedup_key == "strong"
