"""The one place STRYX calls are written and read.

Implements the stryx context's ``TradeJournalPort`` over the ``stryx_calls``
table. Two reads matter: ``live_call_count_today`` (the number that enforces the
daily cap) and ``today`` (the day's journal view). Both bound "today" to the IST
trading day, converted to UTC for the timestamp column — the same day boundary
the Redis session store and the frontend use, so the cap resets with the session.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import func, select

from marketcompass.contexts.stryx.application.ports import JournalEntry, TradeJournalPort
from marketcompass.contexts.stryx.domain.call_template import Status, StryxCall
from marketcompass.infrastructure.persistence.postgresql.models.stryx.stryx_call import (
    StryxCallRecord,
)
from marketcompass.infrastructure.persistence.postgresql.session import Database
from marketcompass.shared_kernel.types.identifiers import TenantId

# India observes no DST, so a fixed +05:30 offset is correct.
_IST = timezone(timedelta(hours=5, minutes=30))


def _ist_day_start_utc(now: datetime | None = None) -> datetime:
    """Midnight IST of the current IST day, expressed in UTC for timestamp filters."""
    now_ist = (now or datetime.now(UTC)).astimezone(_IST)
    midnight_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_ist.astimezone(UTC)


class SqlAlchemyStryxCallRepository:
    """Writes and reads STRYX calls for one tenant at a time.

    Owns short-lived sessions instead of borrowing the request's. STRYX journals
    from inside a ``StreamingResponse`` body, which runs *after* the request-scoped
    session's unit of work has ended — a row flushed onto that session is never
    committed, so every call was silently dropped and the daily LIVE cap could
    never bite. Each method therefore opens its own session; ``append`` commits.
    """

    def __init__(self, database: Database) -> None:
        self._db = database

    async def append(
        self,
        tenant_id: TenantId,
        call: StryxCall,
        *,
        question: str,
        raw_answer: str,
        source: str,
    ) -> None:
        record = StryxCallRecord(
            tenant_id=tenant_id,
            question=question,
            status=call.status.value,
            instrument=call.instrument,
            entry_style=call.entry_style,
            entry=call.entry,
            stop=call.stop,
            target1=call.target1,
            target2=call.target2,
            confidence=call.confidence,
            reasoning=call.reasoning,
            raw_answer=raw_answer,
            source=source if source in ("live", "mock") else "live",
        )
        async with self._db.session() as session:
            session.add(record)

    async def live_call_count_today(self, tenant_id: TenantId) -> int:
        stmt = (
            select(func.count())
            .select_from(StryxCallRecord)
            .where(
                StryxCallRecord.tenant_id == tenant_id,
                StryxCallRecord.status == Status.LIVE.value,
                StryxCallRecord.created_at >= _ist_day_start_utc(),
            )
        )
        async with self._db.read_session() as session:
            return int((await session.execute(stmt)).scalar_one())

    async def today(self, tenant_id: TenantId) -> tuple[JournalEntry, ...]:
        stmt = (
            select(StryxCallRecord)
            .where(
                StryxCallRecord.tenant_id == tenant_id,
                StryxCallRecord.created_at >= _ist_day_start_utc(),
            )
            .order_by(StryxCallRecord.created_at.desc())
        )
        async with self._db.read_session() as session:
            records = (await session.execute(stmt)).scalars().all()
            return tuple(_to_entry(record) for record in records)


def _to_entry(record: StryxCallRecord) -> JournalEntry:
    return JournalEntry(
        created_at=record.created_at,
        instrument=record.instrument,
        entry_style=record.entry_style,
        status=record.status,
        entry=record.entry,
        stop=record.stop,
        target1=record.target1,
        target2=record.target2,
        confidence=record.confidence,
        reasoning=record.reasoning,
    )


# Structural check: the repository satisfies the port.
_: type[TradeJournalPort] = SqlAlchemyStryxCallRepository
