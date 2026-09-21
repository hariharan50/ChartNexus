"""instrument reference price

Revision ID: d58a3926e330
Revises: a7f101050a44
Created: 2026-09-20 16:00:21.133403+00:00

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


revision: str = "d58a3926e330"
down_revision: str | None = "a7f101050a44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable and backfilled by the next catalog sync, so this is a metadata-
    # only change: no table rewrite, safe while the previous release serves.
    op.add_column(
        "instruments",
        sa.Column("reference_price", sa.Numeric(precision=18, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("instruments", "reference_price")
