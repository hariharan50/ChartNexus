"""A small, bounded cache of price candles.

The broker only answers "the last N days of bars" live, per request. This table
keeps the most recent few days of what those calls returned so the chart has a
durable fallback when the broker is unreachable — and, just as importantly, so it
stays small: rows older than the retention window are deleted on every write, so
the table never grows without bound the way an unpruned archive would.

It is a cache, not a source of truth. Live is always fetched first and is fresher
than anything here; these rows exist only to survive an outage and to bound
storage. Candles are global per instrument+interval, not tenant-scoped — the
price of NIFTY is the same fact for everyone.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from marketcompass.infrastructure.persistence.postgresql.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class PriceCandleRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "price_candles"

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The bar size, e.g. ``5m`` — the ``CandleInterval`` value.
    interval: Mapped[str] = mapped_column(String(4), nullable=False)
    #: The bar's opening instant, UTC. The natural key alongside symbol+interval.
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    open: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: Provenance of the fetch this bar came from — only real data is cached.
    source: Mapped[str] = mapped_column(String(8), nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "interval", "bucket_start", name="uq_price_candles_bar"),
        Index("ix_price_candles_lookup", "symbol", "interval", "bucket_start"),
    )
