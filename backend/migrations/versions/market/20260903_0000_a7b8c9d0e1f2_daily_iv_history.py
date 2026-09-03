"""daily iv history

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Created: 2026-09-03 00:00:00+00:00

Checklist before merging:
  - Is this migration safe to run while the previous release is still serving?
    (no dropped columns still referenced, no blocking table rewrites)
  - Are new indexes created CONCURRENTLY on large tables?
  - Does downgrade() actually reverse upgrade(), or is it deliberately absent?

A new, empty table — nothing reads it until the rollup writes to it, so this is
safe to run ahead of the release. It stays small by construction: one row per
instrument per session, ~250 a year.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_iv_history",
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("atm_iv", sa.Numeric(precision=7, scale=3), nullable=False),
        sa.Column("future_close", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("captures", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("atm_iv > 0", name=op.f("ck_daily_iv_history_atm_iv_positive")),
        sa.CheckConstraint("captures > 0", name=op.f("ck_daily_iv_history_captures_positive")),
        sa.CheckConstraint(
            "source in ('live', 'mock')", name=op.f("ck_daily_iv_history_source_known")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_iv_history")),
        sa.UniqueConstraint("symbol", "session_date", name="uq_daily_iv_history_session"),
    )
    op.create_index(
        "ix_daily_iv_history_lookup",
        "daily_iv_history",
        ["symbol", "session_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_daily_iv_history_lookup", table_name="daily_iv_history")
    op.drop_table("daily_iv_history")
