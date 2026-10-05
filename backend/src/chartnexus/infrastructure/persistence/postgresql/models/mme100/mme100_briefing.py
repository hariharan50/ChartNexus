"""Persisted MME100 pre-market briefings — one row per tenant x trading day.

Each row is the morning's full six-section analysis as markdown, plus the
instruments it covered and whether the reads were live or simulated. One briefing
per tenant per day: the worker upserts on ``(tenant_id, trading_day)`` so a re-run
replaces rather than duplicates. Tenant-scoped: a briefing belongs to the tenant
it was generated for.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from chartnexus.infrastructure.persistence.postgresql.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Mme100BriefingRecord(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "mme100_briefings"

    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    instruments: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(8), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "trading_day", name="uq_mme100_briefing_tenant_day"),
    )
