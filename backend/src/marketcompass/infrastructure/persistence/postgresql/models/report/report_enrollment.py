"""Per-tenant opt-in for the scheduled daily report.

Off by default: the report spends the tenant owner's LLM tokens each morning, so a
tenant only runs when it has explicitly opted in. One row per tenant.
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


class ReportEnrollmentRecord(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "report_enrollment"

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    __table_args__ = (UniqueConstraint("tenant_id", name="uq_report_enrollment_tenant"),)
