"""Which tenants the scheduled report worker runs for, and whose key it uses.

Active owners of tenants that opted the report on (joined against
``report_enrollment``), each paired with the founding owner user whose saved LLM
key the narrator uses. Off by default: no enrollment row -> not returned.
"""

from __future__ import annotations

from sqlalchemy import select

from chartnexus.contexts.report.application.ports import EnrolledTenant, TenantDirectoryPort
from chartnexus.infrastructure.persistence.postgresql.models.identity.user import UserRecord
from chartnexus.infrastructure.persistence.postgresql.models.report.report_enrollment import (
    ReportEnrollmentRecord,
)
from chartnexus.infrastructure.persistence.postgresql.session import Database
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId


class SqlAlchemyReportTenantDirectory:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def enrolled_tenants(self) -> tuple[EnrolledTenant, ...]:
        stmt = (
            select(UserRecord.tenant_id, UserRecord.id)
            .join(
                ReportEnrollmentRecord,
                ReportEnrollmentRecord.tenant_id == UserRecord.tenant_id,
            )
            .where(
                UserRecord.status == "active",
                UserRecord.roles.contains(["owner"]),
                ReportEnrollmentRecord.enabled.is_(True),
            )
            .order_by(UserRecord.created_at.asc())
        )
        async with self._db.read_session() as session:
            rows = (await session.execute(stmt)).all()

        seen: dict[TenantId, EnrolledTenant] = {}
        for tenant_id, user_id in rows:
            tid = TenantId(tenant_id)
            if tid not in seen:
                seen[tid] = EnrolledTenant(tenant_id=tid, owner_user_id=UserId(user_id))
        return tuple(seen.values())


# Structural check: the adapter satisfies the port.
_: type[TenantDirectoryPort] = SqlAlchemyReportTenantDirectory
