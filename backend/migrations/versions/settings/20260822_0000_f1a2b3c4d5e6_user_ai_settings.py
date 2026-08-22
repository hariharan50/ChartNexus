"""user ai settings

Revision ID: f1a2b3c4d5e6
Revises: d1e2f3a4b5c6
Created: 2026-08-22 00:00:00.000000+00:00

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

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_ai_settings",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("api_key_enc", sa.Text(), nullable=True),
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
            "provider in ('anthropic', 'openai', 'openrouter')",
            name=op.f("ck_user_ai_settings_ai_provider_known"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_ai_settings")),
    )
    op.create_index(
        "ix_user_ai_settings_tenant_id", "user_ai_settings", ["tenant_id"], unique=False
    )
    # One settings row per user — the repository upsert relies on this.
    op.create_index("uq_user_ai_settings_user", "user_ai_settings", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_user_ai_settings_user", table_name="user_ai_settings")
    op.drop_index("ix_user_ai_settings_tenant_id", table_name="user_ai_settings")
    op.drop_table("user_ai_settings")
