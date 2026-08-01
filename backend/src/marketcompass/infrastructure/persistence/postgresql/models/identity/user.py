"""Identity tables."""

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
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from marketcompass.infrastructure.persistence.postgresql.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class UserRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Stored already normalised (lowercased, NFKC) by the EmailAddress value
    # object; the unique index then makes case-variant duplicates impossible.
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'active'"))

    # Nullable: accounts created through Google have no password at all, which
    # is what makes "this account uses SSO" a fact rather than a guess.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    roles: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), nullable=False, server_default=text("ARRAY['owner']::varchar[]")
    )

    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    identities: Mapped[list[FederatedIdentityRecord]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "status in ('active', 'pending_verification', 'suspended', 'deactivated')",
            name="status_known",
        ),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_non_negative"),
    )


class FederatedIdentityRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A link between a local user and an external identity provider account."""

    __tablename__ = "federated_identities"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    # The provider's immutable user id — Google's `sub`. Not the email, which
    # the user can change.
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)

    user: Mapped[UserRecord] = relationship(back_populates="identities")

    __table_args__ = (
        # One provider account maps to at most one local user, and a user has at
        # most one account per provider.
        UniqueConstraint("provider", "subject", name="uq_federated_identities_provider_subject"),
        UniqueConstraint("user_id", "provider", name="uq_federated_identities_user_id_provider"),
        CheckConstraint("provider in ('password', 'google')", name="provider_known"),
        Index("ix_federated_identities_email", "email"),
    )
