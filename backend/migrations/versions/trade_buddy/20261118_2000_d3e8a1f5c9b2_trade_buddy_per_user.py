"""trade buddy per user: per-user watch state, encrypted alert targets

Revision ID: d3e8a1f5c9b2
Revises: b7c4e1d9a2f6
Created: 2026-11-18 20:00:00.000000+00:00

Trade Buddy was a single-operator tool: one set of levels per instrument, kept
in JSON files, and alerts sent to whichever bot was connected first. This makes
it per-user.

* ``trade_buddy_watch_states``: one row per (user, instrument) holding the
  state document the JSON file used to — marks, watcher states, runtime
  counters, overrides and the day's alert history.
* ``trade_buddy_channels.target`` (Telegram chat id / WhatsApp phone number)
  becomes ``target_enc``: AES-256-GCM ciphertext, bound to its
  (user, channel, ``target``) slot exactly as ``secret_enc`` already is. A phone
  number is personal data and a chat id is half of what a stolen token needs,
  so neither is kept in plaintext.
* Both tables get ``user_id -> users.id ON DELETE CASCADE``: deleting a user
  deletes their levels, their bot token and their phone number with them.

**This migration needs ``CN_SECURITY_ENCRYPTION_KEY``** — the same key the
application runs with — because it encrypts the existing targets in place. The
``migrate`` release task already runs with the backend environment.

Checklist before merging:
  - Is this migration safe to run while the previous release is still serving?
    No, not for Trade Buddy: the previous release reads and writes the plaintext
    ``target`` column this drops, so its channel routes and watcher would fail
    until the new release is up. Deploy them together (``deploy.sh`` runs the
    migration and then starts the new release). Nothing else is affected.
  - Are new indexes created CONCURRENTLY on large tables?
    Not needed: the new table is created empty, and ``trade_buddy_channels``
    holds at most two rows per user.
  - Does downgrade() actually reverse upgrade()?
    Yes. It decrypts the targets back into a plaintext column and drops the new
    table. Per-user watch state has nowhere to go in the old schema and is
    dropped; it is a daily artefact. A target that will not decrypt is cleared
    and its row marked unverified, which the old release reads as "reconnect".
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d3e8a1f5c9b2"
down_revision: str | None = "b7c4e1d9a2f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHANNELS = "trade_buddy_channels"
_STATES = "trade_buddy_watch_states"
_CHANNELS_FK = "fk_trade_buddy_channels_user_id_users"


def _cipher():  # type: ignore[no-untyped-def]
    """The cipher the alert-channel repository uses — same key, same purpose."""
    from chartnexus.bootstrap.settings import get_settings  # noqa: PLC0415
    from chartnexus.infrastructure.security.encryption import AesGcmCipher  # noqa: PLC0415

    security = get_settings().security
    return AesGcmCipher.derive(
        security.encryption_key.get_secret_value(),
        purpose="messaging-credentials",
        previous_secrets=security.retired_encryption_keys,
    )


def _target_aad(user_id: object, channel: str) -> str:
    # Must match `_aad(..., "target")` in alert_channel_repository.py.
    return f"trade_buddy:{user_id}:{channel}:target"


def upgrade() -> None:
    # -- per-user watch state ------------------------------------------------
    op.create_table(
        _STATES,
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_trade_buddy_watch_states_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trade_buddy_watch_states")),
    )
    op.create_index(op.f("ix_trade_buddy_watch_states_tenant_id"), _STATES, ["tenant_id"])
    op.create_index("ix_trade_buddy_watch_states_symbol", _STATES, ["symbol"])
    op.create_index(
        "uq_trade_buddy_watch_states_user_symbol", _STATES, ["user_id", "symbol"], unique=True
    )

    # -- channels: belong to a user ------------------------------------------
    # A row whose user no longer exists can never be reached through the API
    # and must not survive into a table that now promises cascade deletion.
    op.execute(f"delete from {_CHANNELS} c where not exists (select 1 from users u where u.id = c.user_id)")
    op.create_foreign_key(_CHANNELS_FK, _CHANNELS, "users", ["user_id"], ["id"], ondelete="CASCADE")

    # -- channels: encrypt the target ----------------------------------------
    op.add_column(_CHANNELS, sa.Column("target_enc", sa.Text(), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"select id, user_id, channel, target from {_CHANNELS} where target is not null")
    ).fetchall()
    if rows:
        cipher = _cipher()
        for row in rows:
            bind.execute(
                sa.text(f"update {_CHANNELS} set target_enc = :enc where id = :id"),
                {"enc": cipher.encrypt(row.target, aad=_target_aad(row.user_id, row.channel)), "id": row.id},
            )
    op.drop_column(_CHANNELS, "target")


def downgrade() -> None:
    op.add_column(_CHANNELS, sa.Column("target", sa.String(length=64), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"select id, user_id, channel, target_enc from {_CHANNELS} where target_enc is not null")
    ).fetchall()
    if rows:
        from chartnexus.infrastructure.security.encryption import DecryptionError  # noqa: PLC0415

        cipher = _cipher()
        for row in rows:
            try:
                plain: str | None = cipher.decrypt(
                    row.target_enc, aad=_target_aad(row.user_id, row.channel)
                )
            except DecryptionError:
                plain = None
            if plain is None:
                # Cannot be recovered under this key: leave the row needing a
                # reconnect rather than inventing a target.
                bind.execute(
                    sa.text(f"update {_CHANNELS} set verified = false where id = :id"),
                    {"id": row.id},
                )
            else:
                bind.execute(
                    sa.text(f"update {_CHANNELS} set target = :target where id = :id"),
                    {"target": plain, "id": row.id},
                )
    op.drop_column(_CHANNELS, "target_enc")
    op.drop_constraint(_CHANNELS_FK, _CHANNELS, type_="foreignkey")

    op.drop_index("uq_trade_buddy_watch_states_user_symbol", table_name=_STATES)
    op.drop_index("ix_trade_buddy_watch_states_symbol", table_name=_STATES)
    op.drop_index(op.f("ix_trade_buddy_watch_states_tenant_id"), table_name=_STATES)
    op.drop_table(_STATES)
