"""price candles cache

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5a6
Created: 2026-08-14 00:00:00+00:00

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

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "price_candles",
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("interval", sa.String(length=4), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("high", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("low", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("close", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_candles")),
        sa.UniqueConstraint("symbol", "interval", "bucket_start", name="uq_price_candles_bar"),
    )
    op.create_index(
        "ix_price_candles_lookup",
        "price_candles",
        ["symbol", "interval", "bucket_start"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_price_candles_lookup", table_name="price_candles")
    op.drop_table("price_candles")
