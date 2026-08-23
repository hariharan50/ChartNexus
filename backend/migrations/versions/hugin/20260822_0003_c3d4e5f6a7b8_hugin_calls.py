"""hugin calls

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Created: 2026-08-22 00:03:00.000000+00:00

Checklist before merging:
  - Is this migration safe to run while the previous release is still serving?
  - Are new indexes created CONCURRENTLY on large tables?
  - Does downgrade() actually reverse upgrade(), or is it deliberately absent?
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hugin_calls",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("instrument", sa.String(length=64), nullable=False),
        sa.Column("bias", sa.String(length=16), nullable=False),
        sa.Column("target_zone", sa.Text(), nullable=False),
        sa.Column("conviction", sa.Numeric(), nullable=False),
        sa.Column("track_hit_rate", sa.Numeric(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("entry", sa.String(length=64), nullable=True),
        sa.Column("stop", sa.String(length=64), nullable=True),
        sa.Column("target1", sa.String(length=64), nullable=True),
        sa.Column("target2", sa.String(length=64), nullable=True),
        sa.Column("grade", sa.String(length=8), nullable=True),
        sa.Column("score", sa.Numeric(), nullable=True),
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
            name=op.f("ck_hugin_calls_bias_known"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hugin_calls")),
    )
    op.create_index(op.f("ix_hugin_calls_tenant_id"), "hugin_calls", ["tenant_id"], unique=False)
    op.create_index(
        "ix_hugin_calls_lookup",
        "hugin_calls",
        ["tenant_id", "instrument", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_hugin_calls_lookup", table_name="hugin_calls")
    op.drop_index(op.f("ix_hugin_calls_tenant_id"), table_name="hugin_calls")
    op.drop_table("hugin_calls")
