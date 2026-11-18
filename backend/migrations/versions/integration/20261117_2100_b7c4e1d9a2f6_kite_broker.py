"""kite broker: one active broker per tenant, Client ID binding, Kite catalog

Revision ID: b7c4e1d9a2f6
Revises: f4a9c2d7e1b3
Created: 2026-11-17 21:00:00.000000+00:00

Adds Zerodha Kite as a second market-data broker (ADR 0002).

* ``broker_connections.broker`` may now be ``kite``.
* The "one live connection per tenant per broker" index becomes "one live
  connection per tenant": a tenant is one user, and one broker serves their
  data at a time. Credentials for both brokers can still be stored, so a
  second, non-partial unique index keeps it to one row per tenant per broker.
* ``client_id``: the broker login id a connection is bound to (not secret).
* ``kite_instruments``: Zerodha's daily instrument dump, needed because Kite
  streams and serves history by integer token and has no option-chain
  endpoint.

Checklist before merging:
  - Is this migration safe to run while the previous release is still serving?
    Yes. The previous release only ever writes ``broker = 'fyers'``, so the
    one-active-per-tenant index cannot be violated by it (it allowed one active
    row per (tenant, fyers), which is one per tenant). The new nullable column
    and the new table are ignored by the old code.
  - Are new indexes created CONCURRENTLY on large tables?
    Not needed: ``broker_connections`` holds one or two rows per tenant, and
    ``kite_instruments`` is created empty.
  - Does downgrade() actually reverse upgrade()?
    Yes, except it refuses while Kite rows exist — narrowing the broker check
    would otherwise fail halfway. Delete them first if a downgrade is intended.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c4e1d9a2f6"
down_revision: str | None = "f4a9c2d7e1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_broker_connections_broker_known"), "broker_connections", type_="check"
    )
    op.create_check_constraint(
        "broker_known",
        "broker_connections",
        "broker in ('fyers', 'kite')",
    )

    op.drop_index("uq_broker_connections_active", table_name="broker_connections")
    op.create_index(
        "uq_broker_connections_one_active",
        "broker_connections",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_broker_connections_tenant_broker",
        "broker_connections",
        ["tenant_id", "broker"],
        unique=True,
    )

    op.add_column("broker_connections", sa.Column("client_id", sa.String(16), nullable=True))

    op.create_table(
        "kite_instruments",
        sa.Column("instrument_token", sa.BigInteger(), nullable=False),
        sa.Column("exchange", sa.String(8), nullable=False),
        sa.Column("segment", sa.String(16), nullable=False),
        sa.Column("tradingsymbol", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), server_default=sa.text("''"), nullable=False),
        sa.Column("instrument_type", sa.String(8), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=True),
        sa.Column("strike", sa.Numeric(14, 4), nullable=True),
        sa.Column("lot_size", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("tick_size", sa.Numeric(10, 4), server_default=sa.text("0.05"), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("instrument_token", name=op.f("pk_kite_instruments")),
    )
    op.create_index(
        "ix_kite_instruments_exchange_symbol", "kite_instruments", ["exchange", "tradingsymbol"]
    )
    op.create_index(
        "ix_kite_instruments_name_segment_expiry",
        "kite_instruments",
        ["name", "segment", "expiry"],
    )
    op.create_index("ix_kite_instruments_type", "kite_instruments", ["instrument_type"])


def downgrade() -> None:
    bind = op.get_bind()
    kite_rows = bind.execute(
        sa.text("select count(*) from broker_connections where broker = 'kite'")
    ).scalar_one()
    if kite_rows:
        msg = (
            f"{kite_rows} Kite broker connection(s) exist; delete them before downgrading, "
            "or the narrowed broker check cannot be created."
        )
        raise RuntimeError(msg)

    op.drop_index("ix_kite_instruments_type", table_name="kite_instruments")
    op.drop_index("ix_kite_instruments_name_segment_expiry", table_name="kite_instruments")
    op.drop_index("ix_kite_instruments_exchange_symbol", table_name="kite_instruments")
    op.drop_table("kite_instruments")

    op.drop_column("broker_connections", "client_id")

    op.drop_index("uq_broker_connections_tenant_broker", table_name="broker_connections")
    op.drop_index("uq_broker_connections_one_active", table_name="broker_connections")
    op.create_index(
        "uq_broker_connections_active",
        "broker_connections",
        ["tenant_id", "broker"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.drop_constraint(
        op.f("ck_broker_connections_broker_known"), "broker_connections", type_="check"
    )
    op.create_check_constraint(
        "broker_known",
        "broker_connections",
        "broker in ('fyers')",
    )
