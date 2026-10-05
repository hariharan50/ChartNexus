"""Persisted HUGIN calls — the memory-driven, saved trade calls.

One row per call HUGIN issues from its memory. Keeps both the analytical read
(bias, target zone, conviction) and the trade structure (entry/stop/targets), plus
``track_hit_rate`` — HUGIN's measured record at call time — so conviction can be
read honestly. Entry/stop/target are free text because HUGIN quotes zones, not
bare prices (the ``stryx_calls`` convention). Grade columns are reserved for a
later auto-grading phase.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from chartnexus.infrastructure.persistence.postgresql.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class HuginCallRecord(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "hugin_calls"

    instrument: Mapped[str] = mapped_column(String(64), nullable=False)
    bias: Mapped[str] = mapped_column(String(16), nullable=False)
    target_zone: Mapped[str] = mapped_column(Text, nullable=False)
    conviction: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    track_hit_rate: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    entry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stop: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target1: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target2: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Reserved for a later auto-grading phase.
    grade: Mapped[str | None] = mapped_column(String(8), nullable=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)

    __table_args__ = (
        Index("ix_hugin_calls_lookup", "tenant_id", "instrument", "created_at"),
        CheckConstraint(
            "bias in ('BULLISH', 'BEARISH', 'NEUTRAL')",
            name="bias_known",
        ),
    )
