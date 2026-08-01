"""Refresh session table.

One row per issued refresh token. Rotation inserts a successor rather than
updating in place, so the chain is auditable: which device, when, and what
ended it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from marketcompass.infrastructure.persistence.postgresql.base import Base, UUIDPrimaryKeyMixin


class RefreshSessionRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "refresh_sessions"

    # All rotations of one login share a family. Revoking a family is how a
    # stolen token is neutralised.
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # SHA-256 of the token. The token itself is never stored, so a dump of this
    # table cannot be replayed.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(String(32))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    generation: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip_address: Mapped[str | None] = mapped_column(String(45))

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_sessions_token_hash"),
        CheckConstraint("expires_at > issued_at", name="expires_after_issue"),
        CheckConstraint("generation >= 0", name="generation_non_negative"),
        Index("ix_refresh_sessions_family_id", "family_id"),
        # Supports "list this user's live sessions" and the session cap, without
        # scanning the revoked history.
        Index(
            "ix_refresh_sessions_user_active",
            "user_id",
            "expires_at",
            postgresql_where=text("revoked_at is null and used_at is null"),
        ),
        # Lets the cleanup job find expired rows cheaply.
        Index("ix_refresh_sessions_expires_at", "expires_at"),
    )
