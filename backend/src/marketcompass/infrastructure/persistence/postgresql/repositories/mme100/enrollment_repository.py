"""The one place MME100's per-tenant opt-in is read and written.

Implements ``EnrollmentStorePort`` over ``mme100_enrollment``. Owns its own
sessions, because both the request-scoped settings API and the request-less worker
read it. An absent row means disabled — the default — so ``is_enabled`` treats "no
row" as ``False``. Writing upserts on the tenant.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from marketcompass.contexts.mme100.application.ports import EnrollmentStorePort
from marketcompass.infrastructure.persistence.postgresql.models.mme100.mme100_enrollment import (
    Mme100EnrollmentRecord,
)
from marketcompass.infrastructure.persistence.postgresql.session import Database
from marketcompass.shared_kernel.types.identifiers import TenantId


class SqlAlchemyMme100EnrollmentRepository:
    """Reads and writes the per-tenant MME100 opt-in flag."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def is_enabled(self, tenant_id: TenantId) -> bool:
        stmt = select(Mme100EnrollmentRecord.enabled).where(
            Mme100EnrollmentRecord.tenant_id == tenant_id
        )
        async with self._db.read_session() as session:
            result = (await session.execute(stmt)).scalar_one_or_none()
        return bool(result)

    async def set_enabled(self, tenant_id: TenantId, enabled: bool) -> None:
        statement = pg_insert(Mme100EnrollmentRecord).values(tenant_id=tenant_id, enabled=enabled)
        statement = statement.on_conflict_do_update(
            constraint="uq_mme100_enrollment_tenant",
            set_={"enabled": statement.excluded.enabled},
        )
        async with self._db.session() as session:
            await session.execute(statement)


# Structural check: the repository satisfies the port.
_: type[EnrollmentStorePort] = SqlAlchemyMme100EnrollmentRepository
