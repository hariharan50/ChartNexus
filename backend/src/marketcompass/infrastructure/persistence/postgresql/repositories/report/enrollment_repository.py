"""Reads and writes the per-tenant scheduled-report opt-in flag.

Owns its own sessions (like the HUGIN/MME100 stores) because it is read from the
request-less worker as well as the settings API. Absent row = off (the default).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from marketcompass.contexts.report.application.ports import EnrollmentStorePort
from marketcompass.infrastructure.persistence.postgresql.models.report.report_enrollment import (
    ReportEnrollmentRecord,
)
from marketcompass.infrastructure.persistence.postgresql.session import Database
from marketcompass.shared_kernel.types.identifiers import TenantId


class SqlAlchemyReportEnrollmentRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def is_enabled(self, tenant_id: TenantId) -> bool:
        stmt = select(ReportEnrollmentRecord.enabled).where(
            ReportEnrollmentRecord.tenant_id == tenant_id
        )
        async with self._db.read_session() as session:
            return bool((await session.execute(stmt)).scalar_one_or_none())

    async def set_enabled(self, tenant_id: TenantId, enabled: bool) -> None:
        statement = pg_insert(ReportEnrollmentRecord).values(tenant_id=tenant_id, enabled=enabled)
        statement = statement.on_conflict_do_update(
            constraint="uq_report_enrollment_tenant",
            set_={"enabled": statement.excluded.enabled},
        )
        async with self._db.session() as session:
            await session.execute(statement)


# Structural check: the repository satisfies the port.
_: type[EnrollmentStorePort] = SqlAlchemyReportEnrollmentRepository
