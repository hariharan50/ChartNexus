"""instrument indices

Revision ID: 4628494b4ccd
Revises: d58a3926e330
Created: 2026-09-21 01:30:02.253637+00:00

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


revision: str = "4628494b4ccd"
down_revision: str | None = "d58a3926e330"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable and backfilled by the next catalog sync from the curated table,
    # so this is a metadata-only change: no rewrite, safe under the old release.
    op.add_column("instruments", sa.Column("indices", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("instruments", "indices")
