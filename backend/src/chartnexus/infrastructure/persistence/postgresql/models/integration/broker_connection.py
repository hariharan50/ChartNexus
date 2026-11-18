"""Broker connection table.

One row per tenant per broker. Holds the tenant's own API application
credentials and the OAuth token obtained with them — every secret column is
AES-256-GCM ciphertext, never plaintext, and each one is bound to its tenant,
broker, and column name so it cannot be replayed into a different slot.
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

from chartnexus.infrastructure.persistence.postgresql.base import (
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
    # The broker *login* id the user said they would connect as (FYERS
    # "XA12345", Zerodha "AB1234"). Not secret; checked against the profile the
    # broker returns, so an already-signed-in browser cannot connect the wrong
    # account.
    client_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    app_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Text, not String(n): the AES-GCM envelope adds a nonce, tag, and key id
    # on top of base64 expansion, and a token length change must not need a
    # migration.
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
        # The invariant the application relies on: one tenant (one user) has
        # at most ONE live broker connection, whichever broker it is. Credentials
        # for several brokers can be stored; only one serves data at a time.
        Index(
            "uq_broker_connections_one_active",
            "tenant_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        # One row per tenant per broker, in any status.
        Index("uq_broker_connections_tenant_broker", "tenant_id", "broker", unique=True),
        Index("ix_broker_connections_tenant_id", "tenant_id"),
        CheckConstraint(
            "status in ('pending', 'active', 'expired', 'revoked')",
            name="status_known",
        ),
        # No trailing comma: this string is emitted as raw SQL, where
        # "in ('fyers',)" is a syntax error rather than a one-tuple.
        CheckConstraint("broker in ('fyers', 'kite')", name="broker_known"),
        # An active connection without a token would be a lie told to the UI.
        CheckConstraint(
            "status <> 'active' or access_token_enc is not null",
            name="active_requires_token",
        ),
    )
