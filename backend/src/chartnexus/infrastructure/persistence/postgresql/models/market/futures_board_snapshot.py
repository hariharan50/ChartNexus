"""Captured futures-board frames.

The broker only ever answers "now". :class:`OptionChainSnapshotRecord` is this
application's archive of the option chain; this is the same idea for the
futures board, and it is what lets Future Lab draw a real intraday line instead
of the two-point open-vs-now proxy it has been showing.

Frames are global per symbol, not tenant-scoped: the open interest on RELIANCE
futures is the same fact for every user, so storing it once avoids duplicating
identical market data per tenant. ``captured_at`` is the UTC instant of
capture; ``session_date`` is the IST trading date it belongs to, stored
explicitly so day-scoped reads never have to reason about the UTC/IST date
boundary.

**``open_interest`` is nullable, and that is not laziness.** Price arrives from
batched quotes — fifty symbols per request, so the whole universe costs five
calls — while open interest comes from the depth endpoint, which accepts
exactly one symbol per request and therefore costs two hundred and nineteen.
The two cannot share a cadence inside the broker's quota, so a frame captured
between open-interest sweeps carries a price and the last OI known at that
moment, and a frame captured before the first sweep of the day carries no OI at
all. A reader plotting this gets a staircase against a smooth price line, which
is how open interest genuinely behaves; do not interpolate it into something
prettier than the data.
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
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from chartnexus.infrastructure.persistence.postgresql.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class FuturesBoardSnapshotRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "futures_board_snapshots"

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: The front-month futures last-traded price. Not the cash price.
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    #: See the module docstring: absent between sweeps, not zero.
    open_interest: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: The contract this frame priced, so a series spanning a rollover can say
    #: where the discontinuity came from rather than showing an unexplained gap.
    expiry: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Provenance is stored so a synthetic (mock) frame is never mistaken for a
    # real capture. In normal operation only 'live' frames are written.
    source: Mapped[str] = mapped_column(String(8), nullable=False)

    __table_args__ = (
        Index(
            "ix_futures_board_snapshots_lookup",
            "symbol",
            "session_date",
            "captured_at",
        ),
        # One frame per symbol per instant. The worker is restartable and two
        # overlapping sweeps would otherwise double up the series.
        UniqueConstraint(
            "symbol",
            "captured_at",
            name="futures_board_snapshots_symbol_instant",
        ),
        CheckConstraint("price > 0", name="price_positive"),
        CheckConstraint(
            "open_interest is null or open_interest >= 0", name="open_interest_not_negative"
        ),
        CheckConstraint("source in ('live', 'mock')", name="source_known"),
    )
