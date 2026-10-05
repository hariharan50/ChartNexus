"""The instrument catalog table.

Global reference data, deliberately *not* tenant-scoped: the NSE F&O list is the
same for everyone, and copying ~220 identical rows per tenant would buy nothing.

Rows are never deleted. When a symbol leaves the F&O list it is flagged
``is_active = false``, because stored snapshots still refer to it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from chartnexus.infrastructure.persistence.postgresql.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class InstrumentRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "instruments"

    # String(20) matches every other symbol column in the schema
    # (price_candles, option_chain_snapshots, daily_iv_history), so a symbol
    # that fits here fits everywhere it will later be written.
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)

    lot_size: Mapped[int] = mapped_column(nullable=False)
    # Numeric, not float: tick and strike steps are exact decimal quantities
    # (0.05, 2.5) and binary floating point does not represent them exactly.
    tick_size: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    strike_step: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)

    spot_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    futures_root: Mapped[str] = mapped_column(String(32), nullable=False)

    isin: Mapped[str | None] = mapped_column(String(12), nullable=True)
    front_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Comma-separated ISO dates, the same shape as `indices` and for the same
    # reason: three short values read as a whole and never queried by element.
    # Three monthly series at ten characters each fits inside this with room
    # for an exchange that lists more.
    futures_expiries: Mapped[str | None] = mapped_column(String(128), nullable=True)
    underlying_token: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Seed level for mock generation, not a quote. Wide precision: the universe
    # spans IDEA around 10 to BOSCHLTD around 48,000.
    reference_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Comma-separated rather than an array or a join table: it is a handful of
    # short names read as a whole, never queried by element.
    indices: Mapped[str | None] = mapped_column(String(128), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    __table_args__ = (
        # Canonical symbols are unique across the catalog. A stock dual-listed
        # on NSE and BSE is one instrument; the sync prefers its primary venue
        # rather than storing it twice.
        Index("uq_instruments_symbol", "symbol", unique=True),
        # The picker's default query is "active, indices first" — this covers it.
        Index("ix_instruments_active_kind", "is_active", "kind"),
        CheckConstraint("kind in ('index', 'stock')", name="instrument_kind_known"),
        CheckConstraint("lot_size > 0", name="instrument_lot_size_positive"),
    )
