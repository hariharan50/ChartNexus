"""Per-(user, channel) Trade Buddy alert connection.

Deliberately a second table rather than a row in ``channel_connections``: a
level break and a morning briefing want different bots, so that one can be
silenced on the phone without silencing the other. Sharing the messaging table
would have meant widening its ``unique(user, channel)`` invariant and changing
a context MME100, HUGIN and the daily report all depend on.

Same column shape as its neighbour, and for the same reasons — the secret is
AES-256-GCM ciphertext bound to its (user, channel, column) slot, never
plaintext.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from chartnexus.infrastructure.persistence.postgresql.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class AlertChannelRecord(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "trade_buddy_channels"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)

    # Text, not String(n): the AES-GCM envelope adds a nonce, tag and key id on
    # top of base64 expansion, and a key-length change must not need a migration.
    secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Telegram chat id, or the WhatsApp phone number. Null until linked.
    target: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Display label, e.g. the bot's @username. Never a secret.
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    __table_args__ = (
        Index("uq_trade_buddy_channels_user_channel", "user_id", "channel", unique=True),
        CheckConstraint(
            "channel in ('telegram', 'whatsapp')",
            name="trade_buddy_channel_known",
        ),
    )
