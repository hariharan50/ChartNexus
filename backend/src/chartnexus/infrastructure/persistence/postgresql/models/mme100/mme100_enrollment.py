"""Per-tenant MME100 pre-market-briefing opt-in.

The autonomous morning briefing spends the tenant owner's LLM tokens, so it is
**off by default**: a tenant only runs when it has explicitly opted in. One row per
tenant; the absence of a row (or ``enabled = false``) means disabled. The worker's
tenant directory joins on this table, so turning it off stops the briefing at the
next morning's run.
"""

from __future__ import annotations

from sqlalchemy import Boolean, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from chartnexus.infrastructure.persistence.postgresql.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Mme100EnrollmentRecord(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "mme100_enrollment"

    # Off by default: an autonomous, token-spending briefing must be opted into.
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    __table_args__ = (UniqueConstraint("tenant_id", name="uq_mme100_enrollment_tenant"),)
