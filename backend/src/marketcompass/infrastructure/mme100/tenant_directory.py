"""TenantDirectoryPort — who the pre-market worker runs for, and whose key it uses.

The worker has no logged-in user, so it derives its tenant list from the durable
directory: the active tenants that have **opted the briefing on** (joined against
``mme100_enrollment``), each paired with an ``owner``-role user whose saved
``ai_settings`` key the analyst reflects with. The briefing is off by default, so a
tenant with no enrollment row is not returned. A tenant with no active owner is
skipped (there is no key to run on). Owns its own read session, like the other
worker-side repositories.
"""

from __future__ import annotations

from sqlalchemy import select

from marketcompass.contexts.mme100.application.ports import EnrolledTenant, TenantDirectoryPort
from marketcompass.infrastructure.persistence.postgresql.models.identity.user import UserRecord
from marketcompass.infrastructure.persistence.postgresql.models.mme100.mme100_enrollment import (
    Mme100EnrollmentRecord,
)
from marketcompass.infrastructure.persistence.postgresql.session import Database
from marketcompass.shared_kernel.types.identifiers import TenantId, UserId


class SqlAlchemyMme100TenantDirectory:
    """Enumerates enrolled tenants and their owner user."""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def enrolled_tenants(self) -> tuple[EnrolledTenant, ...]:
        # Active owners of tenants that opted the briefing on, oldest first, so
        # "first seen per tenant" picks the founding owner deterministically. The
        # join to mme100_enrollment (enabled = true) is what makes it opt-in: no
        # enrollment row -> the tenant is not returned.
        stmt = (
            select(UserRecord.tenant_id, UserRecord.id)
            .join(
                Mme100EnrollmentRecord,
                Mme100EnrollmentRecord.tenant_id == UserRecord.tenant_id,
            )
            .where(
                UserRecord.status == "active",
                UserRecord.roles.contains(["owner"]),
                Mme100EnrollmentRecord.enabled.is_(True),
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
_: type[TenantDirectoryPort] = SqlAlchemyMme100TenantDirectory
