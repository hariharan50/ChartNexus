"""add user phone

Revision ID: 4c31c4255210
Revises: 997e5e90aae3
Created: 2026-08-05 09:55:43.115827+00:00

Adds the phone number captured at sign-up, which doubles as a sign-in
identifier alongside the email address.

Both columns are nullable and added without a default, so this is a metadata-
only change — safe against a running previous release. Nullable is not just for
that: accounts created before this migration, and Google sign-ups, genuinely
have no number. SQL treats NULLs as distinct, so `uq_users_phone` still allows
any number of phone-less rows while forbidding two accounts sharing a number.

`phone_verified_at` is written by nothing today; it exists so the SMS/OTP flow
can land later without another migration of this shape.

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


revision: str = "4c31c4255210"
down_revision: str | None = "997e5e90aae3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=16), nullable=True))
    op.add_column(
        "users", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint("uq_users_phone", "users", ["phone"])
    # Hand-added: Alembic does not autogenerate CHECK constraints. Mirrors the
    # PhoneNumber value object so a hand-written INSERT or a bad backfill cannot
    # store a number sign-in could never match.
    op.create_check_constraint(
        "phone_e164_india",
        "users",
        r"phone is null or phone ~ '^\+91[6-9][0-9]{9}$'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_phone_e164_india", "users", type_="check")
    op.drop_constraint("uq_users_phone", "users", type_="unique")
    op.drop_column("users", "phone_verified_at")
    op.drop_column("users", "phone")
