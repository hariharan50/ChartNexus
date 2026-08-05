"""Captured option-chain snapshots.

The broker only ever answers "now" — it will not say what open interest was at
10:30 this morning. This table is the application's own time-series archive of
the option chain: the ingest process writes one header row (plus its per-strike
:class:`OptionChainRowRecord` children) every few minutes during market hours,
and the Open Interest tool reads them back to draw real intraday history instead
of a two-point open-vs-now proxy.

Snapshots are global per instrument symbol, not tenant-scoped: the open interest
on NIFTY is the same fact for every user, so storing it once avoids duplicating
identical market data per tenant.

``captured_at`` is the UTC instant of capture; ``session_date`` is the IST
trading date it belongs to, stored explicitly so day-scoped reads never have to
reason about the UTC/IST date boundary.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from marketcompass.infrastructure.persistence.postgresql.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from marketcompass.infrastructure.persistence.postgresql.models.market.option_chain_row import (
    OptionChainRowRecord,
)


class OptionChainSnapshotRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "option_chain_snapshots"

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    expiry: Mapped[str | None] = mapped_column(String(10), nullable=True)
    spot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    future_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    lot_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Header metrics denormalised at capture so PCR / max-pain history is a cheap
    # header-only read. The per-strike rows remain the source of truth; a reader
    # is free to recompute from them.
    atm_strike: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_call_oi: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_put_oi: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pcr_oi: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    max_pain_strike: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Provenance is stored so a synthetic (mock) row is never mistaken for a real
    # capture. In normal operation only 'live' rows are written.
    source: Mapped[str] = mapped_column(String(8), nullable=False)

    rows: Mapped[list[OptionChainRowRecord]] = relationship(
        OptionChainRowRecord,
        cascade="all, delete-orphan",
        lazy="selectin",
        passive_deletes=True,
    )

    __table_args__ = (
        Index(
            "ix_option_chain_snapshots_lookup",
            "symbol",
            "session_date",
            "captured_at",
        ),
        CheckConstraint("spot > 0", name="spot_positive"),
        CheckConstraint("source in ('live', 'mock')", name="source_known"),
    )
