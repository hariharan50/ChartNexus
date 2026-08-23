"""Persisted HUGIN lessons — the accumulating per-tenant knowledge base.

One row per distilled learning, keyed by ``dedup_key`` so re-observing the same
pattern upserts onto the existing row (folding its hit/miss tally) rather than
duplicating. The reflect step reads the top rows by reliability back into its
prompt, so a lesson that keeps proving true is consulted more.

Tenant-scoped; ``instrument`` null means a cross-instrument lesson.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from marketcompass.infrastructure.persistence.postgresql.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class HuginLessonRecord(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "hugin_lessons"

    instrument: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    misses: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # The upsert target: one row per (tenant, dedup_key).
        UniqueConstraint("tenant_id", "dedup_key", name="uq_hugin_lessons_dedup"),
        Index("ix_hugin_lessons_lookup", "tenant_id", "instrument"),
    )
