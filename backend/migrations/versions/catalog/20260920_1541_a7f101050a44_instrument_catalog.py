"""instrument catalog

Revision ID: a7f101050a44
Revises: a7b8c9d0e1f2
Created: 2026-09-20 15:41:39.920062+00:00

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


revision: str = "a7f101050a44"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Global reference data: no tenant_id, deliberately. The NSE F&O list is
    # the same for every tenant, and per-tenant copies would buy nothing.
    op.create_table(
        "instruments",
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("exchange", sa.String(length=8), nullable=False),
        sa.Column("lot_size", sa.Integer(), nullable=False),
        sa.Column("tick_size", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("strike_step", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("spot_symbol", sa.String(length=64), nullable=False),
        sa.Column("futures_root", sa.String(length=32), nullable=False),
        sa.Column("isin", sa.String(length=12), nullable=True),
        sa.Column("underlying_token", sa.String(length=32), nullable=True),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            "kind in ('index', 'stock')", name=op.f("ck_instruments_instrument_kind_known")
        ),
        sa.CheckConstraint(
            "lot_size > 0", name=op.f("ck_instruments_instrument_lot_size_positive")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instruments")),
    )
    op.create_index(
        "ix_instruments_active_kind", "instruments", ["is_active", "kind"], unique=False
    )
    op.create_index("uq_instruments_symbol", "instruments", ["symbol"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_instruments_symbol", table_name="instruments")
    op.drop_index("ix_instruments_active_kind", table_name="instruments")
    op.drop_table("instruments")
