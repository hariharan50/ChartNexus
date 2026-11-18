"""One user's Trade Buddy state for one instrument.

The whole of it — marked levels, live watcher states, runtime counters,
overrides and the day's alert history — is one small JSON document, read and
rewritten whole (see ``infrastructure/trade_buddy/document_store.py``). A row
per *(user, instrument)* is what makes Trade Buddy per-user: two people
watching NIFTY have two rows, two sets of levels, and two alert histories.

JSONB rather than columns because the document already has a versioned shape
the engine round-trips, and nothing queries inside it except "are any levels
marked", which the worker asks once every reconcile.

Rows belong to a user and go with them: ``ON DELETE CASCADE``.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from chartnexus.infrastructure.persistence.postgresql.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class WatchStateRecord(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "trade_buddy_watch_states"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Canonical instrument name, e.g. ``NIFTY`` — never a broker symbol.
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        Index("uq_trade_buddy_watch_states_user_symbol", "user_id", "symbol", unique=True),
        Index("ix_trade_buddy_watch_states_symbol", "symbol"),
    )
