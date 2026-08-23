"""messaging channel connections

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Created: 2026-08-23 00:02:00.000000+00:00

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

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_connections",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("secret_enc", sa.Text(), nullable=True),
        sa.Column("target", sa.String(length=64), nullable=True),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
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
        sa.CheckConstraint("channel in ('telegram', 'whatsapp')", name="channel_known"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_connections")),
    )
    op.create_index(
        op.f("ix_channel_connections_tenant_id"),
        "channel_connections",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "uq_channel_connections_user_channel",
        "channel_connections",
        ["user_id", "channel"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_channel_connections_user_channel", table_name="channel_connections")
    op.drop_index(op.f("ix_channel_connections_tenant_id"), table_name="channel_connections")
    op.drop_table("channel_connections")
