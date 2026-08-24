"""report enrollment

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Created: 2026-08-23 00:03:00.000000+00:00

Checklist before merging:
  - Is this migration safe to run while the previous release is still serving?
  - Are new indexes created CONCURRENTLY on large tables?
  - Does downgrade() actually reverse upgrade(), or is it deliberately absent?
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_enrollment",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_enrollment")),
        sa.UniqueConstraint("tenant_id", name="uq_report_enrollment_tenant"),
    )
    op.create_index(
        op.f("ix_report_enrollment_tenant_id"),
        "report_enrollment",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_report_enrollment_tenant_id"), table_name="report_enrollment")
    op.drop_table("report_enrollment")
