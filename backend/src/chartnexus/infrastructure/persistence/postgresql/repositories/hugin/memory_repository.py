"""The one place HUGIN's memory is written and read.

Implements ``MemoryStorePort`` over ``hugin_observations`` and ``hugin_lessons``.

Owns short-lived sessions instead of borrowing a request's: HUGIN writes from a
background worker that runs with no request scope, so — like
``SqlAlchemyStryxCallRepository`` — every method opens its own session
(``session()`` commits, ``read_session()`` never does). "Today" is bound to the
IST trading day, the same boundary the rest of the stack uses.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from chartnexus.contexts.hugin.application.ports import MemoryStorePort
from chartnexus.contexts.hugin.domain.lesson import Lesson
from chartnexus.contexts.hugin.domain.observation import Bias, Grade, Observation
from chartnexus.infrastructure.persistence.postgresql.models.hugin.hugin_lesson import (
    HuginLessonRecord,
)
from chartnexus.infrastructure.persistence.postgresql.models.hugin.hugin_observation import (
    HuginObservationRecord,
)
from chartnexus.infrastructure.persistence.postgresql.session import Database
from chartnexus.shared_kernel.types.identifiers import TenantId

# India observes no DST, so a fixed +05:30 offset is correct.
_IST = timezone(timedelta(hours=5, minutes=30))


def _ist_today() -> date:
    return datetime.now(UTC).astimezone(_IST).date()


class SqlAlchemyHuginMemoryRepository:
    """Reads and writes HUGIN's durable memory for one tenant at a time."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def latest_observation(self, tenant_id: TenantId, instrument: str) -> Observation | None:
        stmt = (
            select(HuginObservationRecord)
            .where(
                HuginObservationRecord.tenant_id == tenant_id,
                HuginObservationRecord.instrument == instrument,
            )
            .order_by(HuginObservationRecord.tick_at.desc())
            .limit(1)
        )
        async with self._db.read_session() as session:
            record = (await session.execute(stmt)).scalar_one_or_none()
            return _to_observation(record) if record is not None else None

    async def append_observation(self, observation: Observation) -> None:
        record = HuginObservationRecord(
            tenant_id=observation.tenant_id,
            instrument=observation.instrument,
            tick_at=observation.tick_at,
            trading_day=observation.trading_day,
            readings=observation.readings,
            bias=observation.bias.value,
            expectation=observation.expectation,
            call_wall=observation.call_wall,
            put_wall=observation.put_wall,
            key_level=observation.key_level,
        )
        async with self._db.session() as session:
            session.add(record)

    async def grade_previous(
        self,
        observation_id: UUID,
        *,
        grade: str,
        score: Decimal,
        evidence: dict[str, Any],
    ) -> None:
        stmt = (
            update(HuginObservationRecord)
            .where(HuginObservationRecord.id == observation_id)
            .values(grade=grade, score=score, grade_evidence=evidence)
        )
        async with self._db.session() as session:
            await session.execute(stmt)

    async def lessons_for(
        self, tenant_id: TenantId, instrument: str, top_k: int
    ) -> tuple[Lesson, ...]:
        # A cross-instrument lesson (instrument is null) applies everywhere, so it
        # is eligible alongside the instrument-specific ones.
        stmt = select(HuginLessonRecord).where(
            HuginLessonRecord.tenant_id == tenant_id,
            (HuginLessonRecord.instrument == instrument) | (HuginLessonRecord.instrument.is_(None)),
        )
        async with self._db.read_session() as session:
            records = (await session.execute(stmt)).scalars().all()
            # Map inside the session: the session rolls back on exit, which expires
            # the ORM instances, so reading their columns afterwards would detach.
            lessons = [_to_lesson(r) for r in records]
        # Rank by reliability in Python: the weight is a derived Laplace-smoothed
        # rate, not a stored column, so ordering it in SQL would duplicate the rule.
        lessons.sort(key=lambda lsn: lsn.reliability, reverse=True)
        return tuple(lessons[:top_k])

    async def upsert_lessons(self, tenant_id: TenantId, lessons: tuple[Lesson, ...]) -> None:
        if not lessons:
            return
        rows = [
            {
                "tenant_id": tenant_id,
                "instrument": lsn.instrument,
                "dedup_key": lsn.dedup_key,
                "text": lsn.text,
                "hits": lsn.hits,
                "misses": lsn.misses,
                "last_seen_at": lsn.last_seen_at or datetime.now(UTC),
            }
            for lsn in lessons
        ]
        statement = pg_insert(HuginLessonRecord).values(rows)
        # Re-seeing a lesson refreshes its text and folds its hit/miss deltas onto
        # the existing tally, so reliability accrues rather than resetting.
        statement = statement.on_conflict_do_update(
            constraint="uq_hugin_lessons_dedup",
            set_={
                "text": statement.excluded.text,
                "instrument": statement.excluded.instrument,
                "hits": HuginLessonRecord.hits + statement.excluded.hits,
                "misses": HuginLessonRecord.misses + statement.excluded.misses,
                "last_seen_at": statement.excluded.last_seen_at,
            },
        )
        async with self._db.session() as session:
            await session.execute(statement)

    async def today(self, tenant_id: TenantId, instrument: str) -> tuple[Observation, ...]:
        stmt = (
            select(HuginObservationRecord)
            .where(
                HuginObservationRecord.tenant_id == tenant_id,
                HuginObservationRecord.instrument == instrument,
                HuginObservationRecord.trading_day == _ist_today(),
            )
            .order_by(HuginObservationRecord.tick_at.asc())
        )
        async with self._db.read_session() as session:
            records = (await session.execute(stmt)).scalars().all()
            return tuple(_to_observation(r) for r in records)

    async def history(
        self, tenant_id: TenantId, instrument: str, days: int
    ) -> tuple[Observation, ...]:
        cutoff = _ist_today() - timedelta(days=max(0, days - 1))
        stmt = (
            select(HuginObservationRecord)
            .where(
                HuginObservationRecord.tenant_id == tenant_id,
                HuginObservationRecord.instrument == instrument,
                HuginObservationRecord.trading_day >= cutoff,
            )
            .order_by(HuginObservationRecord.tick_at.asc())
        )
        async with self._db.read_session() as session:
            records = (await session.execute(stmt)).scalars().all()
            return tuple(_to_observation(r) for r in records)

    async def all_lessons(self, tenant_id: TenantId) -> tuple[Lesson, ...]:
        stmt = (
            select(HuginLessonRecord)
            .where(HuginLessonRecord.tenant_id == tenant_id)
            .order_by(HuginLessonRecord.last_seen_at.desc().nullslast())
        )
        async with self._db.read_session() as session:
            records = (await session.execute(stmt)).scalars().all()
            return tuple(_to_lesson(r) for r in records)


def _to_observation(record: HuginObservationRecord) -> Observation:
    return Observation(
        tenant_id=TenantId(record.tenant_id),
        instrument=record.instrument,
        tick_at=record.tick_at,
        trading_day=record.trading_day,
        readings=record.readings,
        bias=Bias(record.bias),
        expectation=record.expectation,
        call_wall=record.call_wall,
        put_wall=record.put_wall,
        key_level=record.key_level,
        grade=Grade(record.grade) if record.grade is not None else None,
        score=record.score,
        grade_evidence=record.grade_evidence,
        id=record.id,
        created_at=record.created_at,
    )


def _to_lesson(record: HuginLessonRecord) -> Lesson:
    return Lesson(
        dedup_key=record.dedup_key,
        text=record.text,
        instrument=record.instrument,
        hits=record.hits,
        misses=record.misses,
        last_seen_at=record.last_seen_at,
    )


# Structural check: the repository satisfies the port.
_: type[MemoryStorePort] = SqlAlchemyHuginMemoryRepository
