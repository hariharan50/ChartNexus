"""The one place HUGIN calls are written and read.

Implements ``CallStorePort`` over ``hugin_calls``. Owns its own sessions like the
other HUGIN repositories, since calls are written from a request-scoped handler but
the repo keeps the same shape as the memory repo. "Recent" is newest-first for the
UI's calls list.
"""

from __future__ import annotations

from sqlalchemy import select

from marketcompass.contexts.hugin.application.ports import CallStorePort
from marketcompass.contexts.hugin.domain.call import HuginCall
from marketcompass.contexts.hugin.domain.observation import Bias
from marketcompass.infrastructure.persistence.postgresql.models.hugin.hugin_call import (
    HuginCallRecord,
)
from marketcompass.infrastructure.persistence.postgresql.session import Database
from marketcompass.shared_kernel.types.identifiers import TenantId


class SqlAlchemyHuginCallRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def append(self, tenant_id: TenantId, call: HuginCall) -> None:
        record = HuginCallRecord(
            tenant_id=tenant_id,
            instrument=call.instrument,
            bias=call.bias.value,
            target_zone=call.target_zone,
            conviction=call.conviction,
            track_hit_rate=call.track_hit_rate,
            rationale=call.rationale,
            entry=call.entry,
            stop=call.stop,
            target1=call.target1,
            target2=call.target2,
        )
        async with self._db.session() as session:
            session.add(record)

    async def recent(
        self, tenant_id: TenantId, instrument: str, limit: int
    ) -> tuple[HuginCall, ...]:
        stmt = (
            select(HuginCallRecord)
            .where(
                HuginCallRecord.tenant_id == tenant_id,
                HuginCallRecord.instrument == instrument,
            )
            .order_by(HuginCallRecord.created_at.desc())
            .limit(limit)
        )
        async with self._db.read_session() as session:
            records = (await session.execute(stmt)).scalars().all()
            return tuple(_to_call(r) for r in records)


def _to_call(record: HuginCallRecord) -> HuginCall:
    return HuginCall(
        instrument=record.instrument,
        bias=Bias(record.bias),
        target_zone=record.target_zone,
        conviction=record.conviction,
        track_hit_rate=record.track_hit_rate,
        rationale=record.rationale,
        entry=record.entry,
        stop=record.stop,
        target1=record.target1,
        target2=record.target2,
        id=record.id,
        created_at=record.created_at,
    )


# Structural check: the repository satisfies the port.
_: type[CallStorePort] = SqlAlchemyHuginCallRepository
