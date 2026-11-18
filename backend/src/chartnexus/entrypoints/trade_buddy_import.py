"""One-off: move a single-operator install's Trade Buddy files into one user's account.

Before Trade Buddy was per-user it kept one JSON file per instrument under
``CN_TRADE_BUDDY_STATE_DIRECTORY`` (``var/trade_buddy/NIFTY.json``…), belonging
to nobody. Per-user state lives in Postgres, so those files are no longer read.
This copies each file's document — levels, watcher states, overrides, the day's
alert history — verbatim into the named user's rows.

Only the overrides (per-instrument sensitivity) are of lasting value; levels are
a daily artefact. The command is therefore safe to skip, and safe to re-run: it
refuses to overwrite an instrument the user already has state for unless
``--force`` is given. The files are left where they are.

    uv run chartnexus-trade-buddy import-legacy --email you@example.com
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select

from chartnexus.bootstrap.container import Container
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.persistence.postgresql.models.identity.user import UserRecord
from chartnexus.infrastructure.trade_buddy.build_trade_buddy import (
    build_fallback_bands,
    build_store,
)
from chartnexus.infrastructure.trade_buddy.json_level_store import JsonLevelStore
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId

log = get_logger(__name__)


class LegacyImportError(Exception):
    """The import cannot proceed; the message says why."""


@dataclass(frozen=True, slots=True)
class ImportResult:
    imported: tuple[str, ...]
    skipped: tuple[str, ...]


async def import_legacy(
    container: Container, *, email: str, directory: Path, force: bool = False
) -> ImportResult:
    """Copy every ``<symbol>.json`` in ``directory`` into ``email``'s state."""
    async with container.database.read_session() as session:
        user = (
            await session.execute(
                select(UserRecord.id, UserRecord.tenant_id).where(
                    func.lower(UserRecord.email) == email.strip().lower()
                )
            )
        ).one_or_none()
    if user is None:
        raise LegacyImportError(f"no user with email {email!r}")
    if not await asyncio.to_thread(directory.is_dir):
        raise LegacyImportError(f"no legacy state directory at {directory}")

    source = JsonLevelStore(directory=directory, bands=build_fallback_bands(container))
    target = build_store(container, user_id=UserId(user.id), tenant_id=TenantId(user.tenant_id))

    imported: list[str] = []
    skipped: list[str] = []
    for symbol in source.symbols():
        document = await source.export_document(symbol)
        if not document:
            # Unreadable, or a version this code does not understand.
            skipped.append(symbol)
            continue
        if await target.export_document(symbol) and not force:
            log.info("trade_buddy_import_skipped", symbol=symbol, reason="user_has_state")
            skipped.append(symbol)
            continue
        await target.replace_document(symbol, document)
        imported.append(symbol)
        log.info("trade_buddy_imported", symbol=symbol)
    return ImportResult(imported=tuple(imported), skipped=tuple(skipped))
