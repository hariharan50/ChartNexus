"""Postgres readiness probe."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy import text

from chartnexus.infrastructure.persistence.postgresql.session import Database


def postgres_check(database: Database) -> Callable[[], Awaitable[None]]:
    """Build the zero-argument coroutine the health router expects."""

    async def check() -> None:
        async with database.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    return check
