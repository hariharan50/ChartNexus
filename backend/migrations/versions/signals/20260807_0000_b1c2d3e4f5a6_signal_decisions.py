"""signal decisions

Revision ID: b1c2d3e4f5a6
Revises: 4c31c4255210
Created: 2026-08-07 00:00:00.000000+00:00

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


revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "4c31c4255210"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signal_decisions",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision", sa.String(length=4), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("components", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("entry", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("stop", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("target", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("risk_reward", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("suggested_contract", sa.String(length=64), nullable=True),
        sa.Column("provenance_source", sa.String(length=8), nullable=False),
        sa.Column("expiry_ref", sa.String(length=10), nullable=True),
        sa.Column("is_actionable", sa.Boolean(), nullable=False),
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
            "confidence >= 0 and confidence <= 100",
            name=op.f("ck_signal_decisions_confidence_range"),
        ),
        sa.CheckConstraint(
            "decision in ('BUY', 'SELL', 'HOLD')", name=op.f("ck_signal_decisions_decision_known")
        ),
        sa.CheckConstraint(
            "provenance_source in ('live', 'cached', 'mock')",
            name=op.f("ck_signal_decisions_provenance_known"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal_decisions")),
    )
    op.create_index(
        op.f("ix_signal_decisions_tenant_id"),
        "signal_decisions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_signal_decisions_lookup",
        "signal_decisions",
        ["tenant_id", "symbol", "generated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_signal_decisions_lookup", table_name="signal_decisions")
    op.drop_index(op.f("ix_signal_decisions_tenant_id"), table_name="signal_decisions")
    op.drop_table("signal_decisions")
