"""One implied-volatility reading per instrument per trading session.

The reason this table exists at all: **implied volatility is only ever quoted
now**, and the intraday archive that holds it (``option_chain_snapshots``) is
pruned after 30 days. Nothing else in the system remembers what volatility cost
last March, and once the prune runs that day is gone for good — the broker will
not sell it back, because FYERS never quoted IV in the first place (it is
back-solved locally at capture time).

So a page that wants IV Rank or IV Percentile over a year has no source unless
something writes one row per session as the sessions happen. That is this table,
and it is deliberately tiny: one row per symbol per day, ~250 rows a year per
instrument, written by ``RollupDailyIv`` from the archive before the prune sees
it. It accretes forward; it cannot be backfilled past the 30-day window.

Rows are global per instrument symbol, not tenant-scoped, for the same reason
the snapshots are: the volatility on NIFTY is the same fact for every user.

``future_close`` rides along because it is free — the same capture carries it,
and it is the only source of a daily *futures* series anywhere in the system
(``/market/history`` serves the index, never a rolled contract).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from chartnexus.infrastructure.persistence.postgresql.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class DailyIvHistoryRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "daily_iv_history"

    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The IST trading date, stored explicitly so a range read never has to
    #: reason about the UTC/IST boundary.
    session_date: Mapped[date] = mapped_column(Date, nullable=False)

    #: At-the-money implied volatility at the session's last capture, in
    #: volatility points (13.2 means 13.2%), matching how IV is stored and
    #: rendered everywhere else in the system.
    atm_iv: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)

    #: The tradable future at that same capture. Nullable: captures taken
    #: before the column was denormalised carry no future.
    future_close: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    #: How many captures backed the day. A session with two captures is a
    #: thinner reading than one with a hundred, and a percentile that cannot
    #: say which is which invites trusting both equally.
    captures: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Provenance, so a synthetic (mock) row is never mistaken for a real one.
    source: Mapped[str] = mapped_column(String(8), nullable=False)

    __table_args__ = (
        # One row per instrument per session — the rollup upserts on this, so
        # re-running it is idempotent rather than duplicating the day.
        UniqueConstraint("symbol", "session_date", name="uq_daily_iv_history_session"),
        Index("ix_daily_iv_history_lookup", "symbol", "session_date"),
        CheckConstraint("atm_iv > 0", name="atm_iv_positive"),
        CheckConstraint("captures > 0", name="captures_positive"),
        CheckConstraint("source in ('live', 'mock')", name="source_known"),
    )
