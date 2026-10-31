"""trade buddy alert channels

Revision ID: f4a9c2d7e1b3
Revises: c1a7f3b90e42
Created: 2026-10-31 00:00:00.000000+00:00

A second channel table rather than a column on `channel_connections`. Alerts
and briefings want different bots — a level break mid-trade and a once-a-
morning briefing want different notification settings on the phone, and
silencing one must not silence the other. Sharing the messaging table would
have meant widening its `unique(user, channel)` invariant, which MME100, HUGIN
and the daily report all sit on.

Checklist before merging:
  - Is this migration safe to run while the previous release is still serving?
    Yes: a new table only. Nothing reads or writes it until the release that
    adds the routes, and the previous release never touches it.
  - Are new indexes created CONCURRENTLY on large tables?
    Not needed: the table is created empty in this same migration.
  - Does downgrade() actually reverse upgrade()?
    Yes — it drops the table, which is the whole of what upgrade() added.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4a9c2d7e1b3"
down_revision: str | None = "c1a7f3b90e42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trade_buddy_channels",
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
        sa.CheckConstraint(
            "channel in ('telegram', 'whatsapp')",
            name="ck_trade_buddy_channels_trade_buddy_channel_known",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trade_buddy_channels")),
    )
    op.create_index(
        op.f("ix_trade_buddy_channels_tenant_id"),
        "trade_buddy_channels",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "uq_trade_buddy_channels_user_channel",
        "trade_buddy_channels",
        ["user_id", "channel"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_trade_buddy_channels_user_channel", table_name="trade_buddy_channels"
    )
    op.drop_index(
        op.f("ix_trade_buddy_channels_tenant_id"), table_name="trade_buddy_channels"
    )
    op.drop_table("trade_buddy_channels")
