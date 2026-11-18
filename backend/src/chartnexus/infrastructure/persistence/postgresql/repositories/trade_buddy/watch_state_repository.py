"""Per-user Trade Buddy state in Postgres — the store that makes Trade Buddy per-user.

``PostgresLevelStore`` implements the ``LevelStore`` port for **one user**. The
user is bound when the store is built, and every read and write is filtered on
it, so the port keeps its symbol-only methods while two people watching NIFTY
can never see or overwrite each other's levels. The document logic itself is
shared with the file store (:mod:`infrastructure.trade_buddy.document_store`).

Writes are a read-modify-write inside one transaction, with the row locked
``FOR UPDATE``. The API (marking levels, Quick Reset) and the worker (saving
watcher states) both write the same row, from different processes; the lock is
what stops one clobbering the other's change in between its read and its write.
A first write creates the row with ``INSERT … ON CONFLICT DO NOTHING`` so two
concurrent first writes cannot both try to insert.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from chartnexus.contexts.trade_buddy.domain.level import LevelBands
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.persistence.postgresql.models.trade_buddy.watch_state import (
    WatchStateRecord,
)
from chartnexus.infrastructure.persistence.postgresql.session import Database
from chartnexus.infrastructure.trade_buddy.document_store import (
    VERSION,
    Document,
    DocumentLevelStore,
    Mutation,
    is_readable,
)
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId

log = get_logger(__name__)


@dataclass(slots=True)
class PostgresLevelStore(DocumentLevelStore):
    """Implements the ``LevelStore`` port for one user, one row per instrument."""

    database: Database
    user_id: UserId
    tenant_id: TenantId
    bands: LevelBands

    async def _load(self, symbol: str) -> Document:
        stmt = select(WatchStateRecord.document).where(
            WatchStateRecord.user_id == self.user_id,
            WatchStateRecord.symbol == symbol,
        )
        async with self.database.read_session() as session:
            document = (await session.execute(stmt)).scalar_one_or_none()
        if document is None:
            return {}
        if not is_readable(document):
            log.warning("trade_buddy_state_version_mismatch", symbol=symbol)
            return {}
        # A copy, so a caller that edits what it read cannot reach the row.
        return copy.deepcopy(document)

    async def _update(self, symbol: str, mutate: Mutation) -> None:
        async with self.database.session() as session:
            await session.execute(
                insert(WatchStateRecord)
                .values(
                    user_id=self.user_id,
                    tenant_id=self.tenant_id,
                    symbol=symbol,
                    document={"version": VERSION},
                )
                .on_conflict_do_nothing(index_elements=["user_id", "symbol"])
            )
            record = (
                await session.execute(
                    select(WatchStateRecord)
                    .where(
                        WatchStateRecord.user_id == self.user_id,
                        WatchStateRecord.symbol == symbol,
                    )
                    .with_for_update()
                )
            ).scalar_one()
            data = copy.deepcopy(record.document) if is_readable(record.document) else {}
            mutate(data)
            data["version"] = VERSION
            # A new object, so the JSONB column is seen as changed.
            record.document = data

    async def _remove(self, symbol: str) -> None:
        async with self.database.session() as session:
            await session.execute(
                delete(WatchStateRecord).where(
                    WatchStateRecord.user_id == self.user_id,
                    WatchStateRecord.symbol == symbol,
                )
            )


@dataclass(frozen=True, slots=True)
class WatchTarget:
    """One user's instrument with levels marked — something the worker must watch."""

    user_id: UserId
    tenant_id: TenantId
    symbol: str


async def find_watch_targets(
    database: Database, symbols: tuple[str, ...]
) -> tuple[WatchTarget, ...]:
    """Every (user, instrument) with at least one marked level, among ``symbols``.

    Whether the levels are *today's* is left to the engine, which says so on the
    page rather than going silent — the same rule as before this was per-user.
    """
    stmt = (
        select(WatchStateRecord.user_id, WatchStateRecord.tenant_id, WatchStateRecord.symbol)
        .where(
            WatchStateRecord.symbol.in_(symbols),
            WatchStateRecord.document["marks"].isnot(None),
            WatchStateRecord.document["marks"] != [],
        )
        .order_by(WatchStateRecord.user_id, WatchStateRecord.symbol)
    )
    async with database.read_session() as session:
        rows = (await session.execute(stmt)).all()
    return tuple(
        WatchTarget(
            user_id=UserId(row.user_id), tenant_id=TenantId(row.tenant_id), symbol=row.symbol
        )
        for row in rows
    )
