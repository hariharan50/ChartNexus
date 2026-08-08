"""Persisted AI-guider decisions.

One row per *change* in the call for an instrument — the ``GetGuidance`` use case
dedups a 15-second poll down to genuine flips and conviction moves, so this table
is a readable audit of how the guider's view evolved through the session rather
than a firehose of identical rows.

Tenant-scoped: two tenants on different broker connections can see different data
(one live, one mock) and therefore different calls, so a decision belongs to the
tenant it was generated for. ``components`` keeps the full per-skill breakdown as
JSONB so the "why" panel and a future ``outcomes`` grader can reconstruct exactly
what fed a call without re-deriving it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from marketcompass.infrastructure.persistence.postgresql.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class SignalDecisionRecord(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "signal_decisions"

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    # The instant the call was generated. Distinct from created_at only in
    # intent; kept explicit so history reads order on a business field.
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    decision: Mapped[str] = mapped_column(String(4), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)

    # Full per-skill breakdown: [{skill,label,weight,score,headline,details}, ...].
    components: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    entry: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    stop: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    target: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    risk_reward: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    suggested_contract: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # The worst provenance of any input that fed the call — a mock leg makes the
    # whole decision mock, and this column is how a reader knows.
    provenance_source: Mapped[str] = mapped_column(String(8), nullable=False)
    expiry_ref: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_actionable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index(
            "ix_signal_decisions_lookup",
            "tenant_id",
            "symbol",
            "generated_at",
        ),
        CheckConstraint(
            "decision in ('BUY', 'SELL', 'HOLD')", name="decision_known"
        ),
        CheckConstraint(
            "provenance_source in ('live', 'cached', 'mock')", name="provenance_known"
        ),
        CheckConstraint("confidence >= 0 and confidence <= 100", name="confidence_range"),
    )
