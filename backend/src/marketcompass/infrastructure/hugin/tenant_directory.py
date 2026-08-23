"""TenantDirectoryPort — who the worker runs for, and whose key it uses.

The worker has no logged-in user, so it derives its tenant list from the durable
directory: the active tenants that have **opted HUGIN on** (joined against
``hugin_enrollment``), each paired with an ``owner``-role user whose saved
``ai_settings`` key HUGIN reflects with. HUGIN is off by default, so a tenant with
no enrollment row is not returned — the worker spends tokens for nobody until they
opt in. A tenant with no active owner is skipped (there is no key to run on). Owns
its own read session, like the other worker-side repositories.
"""

from __future__ import annotations

from sqlalchemy import select

from marketcompass.contexts.hugin.application.ports import EnrolledTenant
from marketcompass.infrastructure.persistence.postgresql.models.hugin.hugin_enrollment import (
    HuginEnrollmentRecord,
)
from marketcompass.infrastructure.persistence.postgresql.models.identity.user import UserRecord
from marketcompass.infrastructure.persistence.postgresql.session import Database
from marketcompass.shared_kernel.types.identifiers import TenantId, UserId


class SqlAlchemyTenantDirectory:
    """Enumerates enrolled tenants and their owner user."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def enrolled_tenants(self) -> tuple[EnrolledTenant, ...]:
        # Active owners of tenants that opted HUGIN on, oldest first, so "first seen
        # per tenant" picks the founding owner deterministically when a tenant has
        # more than one. The join to hugin_enrollment (enabled = true) is what makes
        # HUGIN opt-in: no enrollment row -> the tenant is not returned.
        stmt = (
            select(UserRecord.tenant_id, UserRecord.id)
            .join(
                HuginEnrollmentRecord,
                HuginEnrollmentRecord.tenant_id == UserRecord.tenant_id,
            )
            .where(
                UserRecord.status == "active",
                UserRecord.roles.contains(["owner"]),
                HuginEnrollmentRecord.enabled.is_(True),
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
