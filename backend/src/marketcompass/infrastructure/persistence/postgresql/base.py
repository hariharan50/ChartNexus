"""Declarative base and the column mixins shared by every table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from marketcompass.infrastructure.persistence.postgresql.metadata import metadata as shared_metadata


class Base(DeclarativeBase):
    """Root of the ORM hierarchy. Persistence only — no domain behaviour here."""

    metadata: ClassVar[MetaData] = shared_metadata

    type_annotation_map = {  # noqa: RUF012
        dict[str, Any]: JSONB,
        uuid.UUID: UUID(as_uuid=True),
    }

    def __repr__(self) -> str:
        identifier = getattr(self, "id", None)
        return f"<{type(self).__name__} id={identifier}>"


class UUIDPrimaryKeyMixin:
    """UUIDv7 primary keys: globally unique like v4, but time-ordered, so index
    locality does not collapse the way it does with random keys.

    ``uuidv7()`` is a built-in as of Postgres 18, which is why the stack pins
    that major version.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )


class TimestampMixin:
    """Row lifecycle timestamps, written by the database rather than the app so
    they stay honest across migrations and manual fixes."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TenantScopedMixin:
    """Marks a table as tenant-owned.

    Every query against these tables must filter on ``tenant_id``; the
    repository base enforces it and tests/security asserts it.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )


class SoftDeleteMixin:
    """Retains rows for audit rather than deleting them."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class OptimisticLockMixin:
    """Version counter for aggregates that concurrent writers can race on."""

    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default=text("1"))
