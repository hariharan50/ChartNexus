"""Catalog rows for the integration database.

``create_app``'s lifespan calls ``load_registry``, which installs whatever the
database holds over the process-level registry — an empty list included. The
suite-wide ``instrument_catalog`` fixture is therefore not enough for the two
modules here that build the app: it is installed before the app starts, and the
app's own startup replaces it.

On a developer machine that goes unnoticed, because their compose database
already carries a synced catalog. Against the fresh database CI creates, it is
the whole difference between a green suite and a red one: the registry ends up
empty, every market endpoint answers 502 ``upstream_unavailable``, and the cold
start falls through to the ~19 MB symbol-master download — whose abandoned
sockets resurface as ``ResourceWarning`` errors against whichever unrelated test
happens to be running when they are finally collected.

Storing the same universe the rest of the suite uses closes both: the app reads
it back at startup, and ``ensure_registry`` finds a populated registry and never
reaches for the network.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest

from chartnexus.bootstrap.settings import DatabaseSettings
from chartnexus.contexts.instrument_catalog.domain.instrument import Instrument
from chartnexus.infrastructure.catalog import registry
from chartnexus.infrastructure.persistence.postgresql.repositories.instrument_catalog.instrument_repository import (
    SqlAlchemyInstrumentRepository,
)
from chartnexus.infrastructure.persistence.postgresql.session import Database

ASYNC_DSN = "postgresql+asyncpg://chartnexus:chartnexus@localhost:5433/chartnexus"


async def _store_if_empty(instruments: Sequence[Instrument]) -> int:
    """Write ``instruments`` to the catalog table, unless it already has rows."""
    database = Database.create(DatabaseSettings(url=ASYNC_DSN), use_pool=False)  # type: ignore[arg-type]
    try:
        async with database.read_session() as session:
            if await SqlAlchemyInstrumentRepository(session).search(limit=None):
                return 0
        async with database.session() as session:
            result = await SqlAlchemyInstrumentRepository(session).replace_all(list(instruments))
        return result.added
    finally:
        await database.dispose()


@pytest.fixture(scope="session", autouse=True)
def stored_instrument_catalog(instrument_catalog: None) -> None:
    """Mirror the suite's in-process catalog into the database.

    Depends on ``instrument_catalog`` so the registry it copies is the known
    universe the rest of the suite asserts against, rather than whatever a
    previous load happened to leave behind.

    Writes only to an empty catalog, and deliberately so: ``replace_all``
    deactivates every symbol it is not handed, so seeding unconditionally would
    quietly reduce a developer's synced catalog to these six rows the first time
    they ran the integration suite against their own compose stack.
    """
    asyncio.run(_store_if_empty(registry.current().all()))
