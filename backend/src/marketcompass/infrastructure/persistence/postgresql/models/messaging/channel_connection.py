"""Per-(user, channel) messaging connection.

One row per user per channel. Holds the channel secret (e.g. a Telegram bot token)
as AES-256-GCM ciphertext bound to (user, channel, column), never plaintext, plus
the resolved delivery target, a display label, and the verified/enabled flags.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from marketcompass.infrastructure.persistence.postgresql.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class ChannelConnectionRecord(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "channel_connections"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)

    # Text, not String(n): the AES-GCM envelope adds a nonce, tag and key id on top
    # of base64 expansion, and a key-length change must not need a migration.
    secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: The delivery target (e.g. Telegram chat id). Null until the chat is linked.
    target: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: A display label (e.g. the bot's @username). Never a secret.
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    __table_args__ = (
        # At most one connection per (user, channel); the repository upsert relies
        # on the id but this guards the invariant.
        Index("uq_channel_connections_user_channel", "user_id", "channel", unique=True),
        CheckConstraint(
            "channel in ('telegram', 'whatsapp')",
            name="channel_known",
        ),
    )
