"""instrument futures expiries

Revision ID: c1a7f3b90e42
Revises: b2e21d34159e
Created: 2026-09-23 14:00:00.000000+00:00

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

revision: str = "c1a7f3b90e42"
down_revision: str | None = "b2e21d34159e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Every listed futures expiry for the underlying, comma-separated ISO
    # dates — the same storage shape as `indices`, and for the same reason:
    # three short values read as a whole, never queried by element.
    #
    # Nullable and backfilled by the next catalog sync from the exchange
    # master, so this is a metadata-only change: no rewrite, and the previous
    # release keeps serving front-month boards throughout.
    op.add_column("instruments", sa.Column("futures_expiries", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("instruments", "futures_expiries")
