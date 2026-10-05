"""Persisted HUGIN observations — one row per tenant x instrument x tick.

Each row is an hourly read: the raw ``readings`` snapshot, the ``bias``, the
falsifiable ``expectation``, and the structural levels. The grade columns
(``grade``, ``score``, ``grade_evidence``) are null on insert and filled by the
*next* tick, which loads this row and judges its expectation against what actually
happened — keeping HUGIN's hit-rate an inspectable, per-tenant track record.

``grade_evidence`` stores the cited actual-vs-expected numbers the verdict rested
on, so any HIT/MISS can be audited after the fact even though an LLM judged it.

Tenant-scoped: memory belongs to the tenant it was generated for. The lookup index
mirrors ``stryx_calls`` — the grader and the "today" read both filter on
``(tenant_id, instrument, tick_at)``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from chartnexus.infrastructure.persistence.postgresql.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class HuginObservationRecord(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "hugin_observations"

    instrument: Mapped[str] = mapped_column(String(64), nullable=False)
    tick_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False)

    # The raw tool snapshot: spot, indicators, PCR(+chg), walls, GEX, VIX, source.
    readings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    bias: Mapped[str] = mapped_column(String(16), nullable=False)
    expectation: Mapped[str] = mapped_column(Text, nullable=False)

    call_wall: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    put_wall: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    key_level: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)

    # Filled when the next tick grades this row.
    grade: Mapped[str | None] = mapped_column(String(8), nullable=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    grade_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index(
            "ix_hugin_observations_lookup",
            "tenant_id",
            "instrument",
            "tick_at",
        ),
        CheckConstraint(
            "bias in ('BULLISH', 'BEARISH', 'NEUTRAL')",
            name="bias_known",
        ),
        CheckConstraint(
            "grade is null or grade in ('HIT', 'PARTIAL', 'MISS')",
            name="grade_known",
        ),
    )
