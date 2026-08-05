"""Per-strike option-chain rows.

One row per listed leg (CE or PE) of one strike, belonging to a captured
snapshot. Illiquid legs a provider did not quote are simply absent — a missing
row is not the same as a zero, and inventing zeros would corrupt PCR and max
pain on read.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from marketcompass.infrastructure.persistence.postgresql.base import (
    Base,
    UUIDPrimaryKeyMixin,
)


class OptionChainRowRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "option_chain_rows"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("option_chain_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )

    strike: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    option_type: Mapped[str] = mapped_column(String(2), nullable=False)

    oi: Mapped[int] = mapped_column(BigInteger, nullable=False)
    oi_change: Mapped[int] = mapped_column(BigInteger, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)

    ltp: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # iv stays nullable end to end: a broker that did not quote it must never be
    # read back as 0.0, which is a real (and wrong) volatility.
    iv: Mapped[Decimal | None] = mapped_column(Numeric(7, 3), nullable=True)
    delta: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)

    __table_args__ = (
        Index("ix_option_chain_rows_snapshot", "snapshot_id", "option_type", "strike"),
        CheckConstraint("strike > 0", name="strike_positive"),
        CheckConstraint("option_type in ('CE', 'PE')", name="option_type_known"),
    )
