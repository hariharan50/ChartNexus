"""stryx calls

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
Created: 2026-08-19 00:00:00.000000+00:00

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

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stryx_calls",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("instrument", sa.String(length=64), nullable=True),
        sa.Column("entry_style", sa.String(length=32), nullable=True),
        sa.Column("entry", sa.String(length=64), nullable=True),
        sa.Column("stop", sa.String(length=64), nullable=True),
        sa.Column("target1", sa.String(length=64), nullable=True),
        sa.Column("target2", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("raw_answer", sa.Text(), nullable=False),
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
        sa.CheckConstraint("source in ('live', 'mock')", name=op.f("ck_stryx_calls_source_known")),
        sa.CheckConstraint(
            "status in ('LIVE', 'NO_TRADE', 'WATCHING')",
            name=op.f("ck_stryx_calls_status_known"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stryx_calls")),
    )
    op.create_index(
        op.f("ix_stryx_calls_tenant_id"),
        "stryx_calls",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_stryx_calls_lookup",
        "stryx_calls",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stryx_calls_lookup", table_name="stryx_calls")
    op.drop_index(op.f("ix_stryx_calls_tenant_id"), table_name="stryx_calls")
    op.drop_table("stryx_calls")
