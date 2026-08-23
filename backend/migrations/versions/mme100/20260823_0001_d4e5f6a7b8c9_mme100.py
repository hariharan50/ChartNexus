"""mme100 briefings and enrollment

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Created: 2026-08-23 00:01:00.000000+00:00

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

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mme100_enrollment",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mme100_enrollment")),
        sa.UniqueConstraint("tenant_id", name="uq_mme100_enrollment_tenant"),
    )
    op.create_index(
        op.f("ix_mme100_enrollment_tenant_id"),
        "mme100_enrollment",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "mme100_briefings",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("trading_day", sa.Date(), nullable=False),
        sa.Column(
            "instruments",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
        ),
        sa.Column("markdown", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mme100_briefings")),
        sa.UniqueConstraint(
            "tenant_id", "trading_day", name="uq_mme100_briefing_tenant_day"
        ),
    )
    op.create_index(
        op.f("ix_mme100_briefings_tenant_id"),
        "mme100_briefings",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_mme100_briefings_tenant_id"), table_name="mme100_briefings")
    op.drop_table("mme100_briefings")
    op.drop_index(op.f("ix_mme100_enrollment_tenant_id"), table_name="mme100_enrollment")
    op.drop_table("mme100_enrollment")
