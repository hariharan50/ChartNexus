"""Zerodha's instrument catalog, as of the last successful daily sync.

Kite quotes by ``EXCHANGE:TRADINGSYMBOL`` but streams and serves history by
an integer ``instrument_token``, and it has no option-chain endpoint at all —
a chain is assembled from the option contracts listed here. So the catalog is
not a convenience; nothing Kite-specific works without it.

Replaced wholesale once a day (validate first, then delete-and-insert in one
transaction), so a bad download never leaves the table half-empty. Only the
segments ChartNexus can use are kept: index spots, catalogued equities, and
NSE/BSE derivatives.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from chartnexus.infrastructure.persistence.postgresql.base import Base


class KiteInstrumentRecord(Base):
    __tablename__ = "kite_instruments"

    instrument_token: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    segment: Mapped[str] = mapped_column(String(16), nullable=False)
    tradingsymbol: Mapped[str] = mapped_column(String(64), nullable=False)
    # For derivatives, the underlying ("NIFTY", "RELIANCE"); for an index
    # spot, Zerodha's display name. Quoted names in the dump are unquoted here.
    name: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''"))
    instrument_type: Mapped[str] = mapped_column(String(8), nullable=False)
    expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    tick_size: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, server_default=text("0.05")
    )
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # Spot and futures lookups by quote symbol.
        Index("ix_kite_instruments_exchange_symbol", "exchange", "tradingsymbol"),
        # Option chains and futures series: one underlying, one segment, by expiry.
        Index("ix_kite_instruments_name_segment_expiry", "name", "segment", "expiry"),
        Index("ix_kite_instruments_type", "instrument_type"),
    )
