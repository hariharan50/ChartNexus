"""The one place MME100 briefings are written and read.

Implements ``BriefingStorePort`` over ``mme100_briefings``. Owns short-lived
sessions instead of borrowing a request's: the worker writes with no request
scope, and the read API only needs a point lookup. ``save`` upserts on
``(tenant_id, trading_day)`` so re-running a morning replaces rather than
duplicates; ``today`` reads the current IST trading day, the same boundary the
Redis session store and the frontend use.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from marketcompass.contexts.mme100.application.ports import Briefing, BriefingStorePort
from marketcompass.infrastructure.persistence.postgresql.models.mme100.mme100_briefing import (
    Mme100BriefingRecord,
)
from marketcompass.infrastructure.persistence.postgresql.session import Database
from marketcompass.shared_kernel.types.identifiers import TenantId

# India observes no DST, so a fixed +05:30 offset is correct.
_IST = timezone(timedelta(hours=5, minutes=30))


def _ist_today(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(_IST).date()


class SqlAlchemyMme100BriefingRepository:
    """Writes and reads MME100 pre-market briefings for one tenant at a time."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, tenant_id: TenantId, briefing: Briefing) -> None:
        statement = pg_insert(Mme100BriefingRecord).values(
            tenant_id=tenant_id,
            trading_day=briefing.trading_day,
            instruments=list(briefing.instruments),
            markdown=briefing.markdown,
            source=briefing.source if briefing.source in ("live", "mock") else "live",
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_mme100_briefing_tenant_day",
            set_={
                "instruments": statement.excluded.instruments,
                "markdown": statement.excluded.markdown,
                "source": statement.excluded.source,
            },
        )
        async with self._db.session() as session:
            await session.execute(statement)

    async def today(self, tenant_id: TenantId) -> Briefing | None:
        stmt = select(Mme100BriefingRecord).where(
            Mme100BriefingRecord.tenant_id == tenant_id,
            Mme100BriefingRecord.trading_day == _ist_today(),
        )
        async with self._db.read_session() as session:
            record = (await session.execute(stmt)).scalar_one_or_none()
            # Map inside the session: attributes are expired once it closes.
            return _to_briefing(record) if record is not None else None


def _to_briefing(record: Mme100BriefingRecord) -> Briefing:
    return Briefing(
        trading_day=record.trading_day,
        instruments=tuple(record.instruments),
        markdown=record.markdown,
        source=record.source,
        created_at=record.created_at,
    )


# Structural check: the repository satisfies the port.
_: type[BriefingStorePort] = SqlAlchemyMme100BriefingRepository
