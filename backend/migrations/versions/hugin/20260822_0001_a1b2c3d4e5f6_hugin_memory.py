"""hugin memory

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Created: 2026-08-22 00:01:00.000000+00:00

Checklist before merging:
  - Is this migration safe to run while the previous release is still serving?
    (no dropped columns still referenced, no blocking table rewrites)
  - Are new indexes created CONCURRENTLY on large tables?
  - Does downgrade() actually reverse upgrade(), or is it deliberately absent?
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hugin_observations",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("instrument", sa.String(length=64), nullable=False),
        sa.Column("tick_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trading_day", sa.Date(), nullable=False),
        sa.Column("readings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("bias", sa.String(length=16), nullable=False),
        sa.Column("expectation", sa.Text(), nullable=False),
        sa.Column("call_wall", sa.Numeric(), nullable=True),
        sa.Column("put_wall", sa.Numeric(), nullable=True),
        sa.Column("key_level", sa.Numeric(), nullable=True),
        sa.Column("grade", sa.String(length=8), nullable=True),
        sa.Column("score", sa.Numeric(), nullable=True),
        sa.Column("grade_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.CheckConstraint(
            "bias in ('BULLISH', 'BEARISH', 'NEUTRAL')",
            name=op.f("ck_hugin_observations_bias_known"),
        ),
        sa.CheckConstraint(
            "grade is null or grade in ('HIT', 'PARTIAL', 'MISS')",
            name=op.f("ck_hugin_observations_grade_known"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hugin_observations")),
    )
    op.create_index(
        op.f("ix_hugin_observations_tenant_id"),
        "hugin_observations",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_hugin_observations_lookup",
        "hugin_observations",
        ["tenant_id", "instrument", "tick_at"],
        unique=False,
    )

    op.create_table(
        "hugin_lessons",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("instrument", sa.String(length=64), nullable=True),
        sa.Column("dedup_key", sa.String(length=128), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("hits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("misses", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hugin_lessons")),
        sa.UniqueConstraint("tenant_id", "dedup_key", name="uq_hugin_lessons_dedup"),
    )
    op.create_index(
        op.f("ix_hugin_lessons_tenant_id"),
        "hugin_lessons",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_hugin_lessons_lookup",
        "hugin_lessons",
        ["tenant_id", "instrument"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_hugin_lessons_lookup", table_name="hugin_lessons")
    op.drop_index(op.f("ix_hugin_lessons_tenant_id"), table_name="hugin_lessons")
    op.drop_table("hugin_lessons")
    op.drop_index("ix_hugin_observations_lookup", table_name="hugin_observations")
    op.drop_index(op.f("ix_hugin_observations_tenant_id"), table_name="hugin_observations")
    op.drop_table("hugin_observations")
