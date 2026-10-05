"""Per-user AI (LLM) settings table.

One row per user. Holds the user's chosen provider and model plus their own LLM
API key — the key column is AES-256-GCM ciphertext, never plaintext, and it is
bound to the user, provider, and column name so it cannot be replayed into a
different row.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from chartnexus.infrastructure.persistence.postgresql.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class UserAiSettingsRecord(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "user_ai_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)

    # Text, not String(n): the AES-GCM envelope adds a nonce, tag, and key id on
    # top of base64 expansion, and a key-length change must not need a migration.
    api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # The invariant the application relies on: at most one settings row per
        # user. Repository upsert depends on it.
        Index("uq_user_ai_settings_user", "user_id", unique=True),
        CheckConstraint(
            "provider in ('anthropic', 'openai', 'openrouter')",
            name="ai_provider_known",
        ),
    )
