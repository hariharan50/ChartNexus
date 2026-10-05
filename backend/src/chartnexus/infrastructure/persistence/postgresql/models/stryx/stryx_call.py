"""Persisted STRYX calls — the discipline spine and the backtest record.

One row per call STRYX issues, whatever the status: LIVE, NO TRADE or WATCHING.
Two jobs:

1. *Enforce the daily cap.* Counting today's ``status = 'LIVE'`` rows for a tenant
   is how the hard "max 2 LIVE calls/day" rule is enforced — from the durable
   journal, never trusted to the model's memory.
2. *Backtest STRYX's hit-rate later,* as its own metric separate from HELLA's
   analysis. The full call is kept (entry/stop/targets plus the raw answer) so a
   future grader can reconstruct exactly what was called.

Tenant-scoped: a call belongs to the tenant it was generated for (two tenants can
see different data — one live, one mock — and so get different calls). Entry/stop/
target are stored as free text, not numbers, because STRYX quotes zones
("23,050-23,080") and contracts ("23100 CE"), not bare prices.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from chartnexus.infrastructure.persistence.postgresql.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class StryxCallRecord(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "stryx_calls"

    # The question that prompted the scan — context for a later backtest.
    question: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(10), nullable=False)
    instrument: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_style: Mapped[str | None] = mapped_column(String(32), nullable=True)

    entry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stop: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target1: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target2: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The full text STRYX emitted, so a grader can reconstruct the call verbatim.
    raw_answer: Mapped[str] = mapped_column(Text, nullable=False)
    # Whether the read behind the call was live or mock data.
    source: Mapped[str] = mapped_column(String(8), nullable=False)

    __table_args__ = (
        Index(
            "ix_stryx_calls_lookup",
            "tenant_id",
            "created_at",
        ),
        CheckConstraint("status in ('LIVE', 'NO_TRADE', 'WATCHING')", name="status_known"),
        CheckConstraint("source in ('live', 'mock')", name="source_known"),
    )
