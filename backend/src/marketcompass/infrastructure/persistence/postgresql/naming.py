"""Deterministic constraint naming.

Without this, Postgres invents names for unnamed constraints and Alembic
autogenerate produces migrations that cannot drop them by name. Every
constraint gets a predictable identifier derived from its table and columns.
"""

from __future__ import annotations

from sqlalchemy import MetaData

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def build_metadata(schema: str | None = None) -> MetaData:
    return MetaData(naming_convention=NAMING_CONVENTION, schema=schema)
