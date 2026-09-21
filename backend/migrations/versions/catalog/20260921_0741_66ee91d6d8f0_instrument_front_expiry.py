"""instrument front expiry

Revision ID: 66ee91d6d8f0
Revises: 4628494b4ccd
Created: 2026-09-21 07:41:25.434207+00:00

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


revision: str = "66ee91d6d8f0"
down_revision: str | None = "4628494b4ccd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable and backfilled by the next catalog sync from the exchange
    # master, so this is a metadata-only change: no rewrite, safe under the
    # previous release.
    op.add_column("instruments", sa.Column("front_expiry", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("instruments", "front_expiry")
