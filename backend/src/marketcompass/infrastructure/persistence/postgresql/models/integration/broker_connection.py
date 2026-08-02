"""Broker connection table.

One row per tenant per broker. Holds the tenant's own API application
credentials and the OAuth token obtained with them — every secret column is
Fernet ciphertext, never plaintext.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from marketcompass.infrastructure.persistence.postgresql.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class BrokerConnectionRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "broker_connections"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    broker: Mapped[str] = mapped_column(String(32), nullable=False)

    # The tenant's own broker API application. The app id is not secret (it
    # appears in the authorization URL); the secret is.
    app_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    app_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Text, not String(n): Fernet ciphertext is ~1.4x the plaintext and a token
    # length change must not need a migration.
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'pending'")
    )

    # Masked profile snapshot from the broker (name, id) for display. Never the
    # raw token response — that can contain credentials.
    profile: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        # The invariant the application relies on: at most one live connection
        # per tenant per broker. A plain index would not enforce it, which the
        # source architecture calls out as a defect in its own schema.
        Index(
            "uq_broker_connections_active",
            "tenant_id",
            "broker",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_broker_connections_tenant_id", "tenant_id"),
        CheckConstraint(
            "status in ('pending', 'active', 'expired', 'revoked')",
            name="status_known",
        ),
        # No trailing comma: this string is emitted as raw SQL, where
        # "in ('fyers',)" is a syntax error rather than a one-tuple.
        CheckConstraint("broker in ('fyers')", name="broker_known"),
        # An active connection without a token would be a lie told to the UI.
        CheckConstraint(
            "status <> 'active' or access_token_enc is not null",
            name="active_requires_token",
        ),
    )
