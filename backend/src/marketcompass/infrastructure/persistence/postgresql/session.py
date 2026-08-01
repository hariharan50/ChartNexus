"""Async engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from marketcompass.bootstrap.settings import DatabaseSettings


@dataclass(slots=True)
class Database:
    """Owns the engine for a process. Build one; dispose it on shutdown."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    @classmethod
    def create(cls, settings: DatabaseSettings, *, use_pool: bool = True) -> Database:
        engine = create_async_engine(
            str(settings.url),
            echo=settings.echo,
            future=True,
            pool_pre_ping=True,
            # Celery forks workers; a shared pool across forks hands the same
            # socket to two processes. Those callers pass use_pool=False.
            poolclass=None if use_pool else NullPool,
            **(
                {
                    "pool_size": settings.pool_size,
                    "max_overflow": settings.max_overflow,
                    "pool_timeout": settings.pool_timeout_seconds,
                    "pool_recycle": settings.pool_recycle_seconds,
                }
                if use_pool
                else {}
            ),
            connect_args={
                "server_settings": {
                    "application_name": "marketcompass",
                    "statement_timeout": str(settings.statement_timeout_ms),
                    "jit": "off",
                }
            },
        )
        session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
        return cls(engine=engine, session_factory=session_factory)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """A session that commits on success and rolls back on any exception."""
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            else:
                await session.commit()

    @asynccontextmanager
    async def read_session(self) -> AsyncIterator[AsyncSession]:
        """A never-committing session for queries and read models."""
        async with self.session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    async def dispose(self) -> None:
        await self.engine.dispose()
