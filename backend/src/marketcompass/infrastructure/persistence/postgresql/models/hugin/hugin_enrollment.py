"""Per-tenant HUGIN opt-in.

HUGIN is autonomous and spends the tenant owner's LLM tokens every hour, so it is
**off by default**: a tenant only runs when it has explicitly opted in. One row per
tenant; the absence of a row (or ``enabled = false``) means disabled. The worker's
tenant directory joins on this table, so turning it off stops HUGIN for that tenant
at the next tick.
"""

from __future__ import annotations

from sqlalchemy import Boolean, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from marketcompass.infrastructure.persistence.postgresql.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class HuginEnrollmentRecord(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "hugin_enrollment"

    # Off by default: an autonomous, token-spending agent must be opted into.
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    __table_args__ = (UniqueConstraint("tenant_id", name="uq_hugin_enrollment_tenant"),)
