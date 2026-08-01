"""The single MetaData every table registers against.

Alembic autogenerate compares the live database to this object, so a model that
is never imported is a model Alembic cannot see. :func:`load_all_models` exists
to make that import happen exactly once, in one obvious place.
"""

from __future__ import annotations

import importlib
import pkgutil

from sqlalchemy import MetaData

from marketcompass.infrastructure.persistence.postgresql.naming import build_metadata

metadata: MetaData = build_metadata()

_MODELS_PACKAGE = "marketcompass.infrastructure.persistence.postgresql.models"


def load_all_models() -> None:
    """Import every module under ``models/`` so its tables attach to metadata.

    Walking the package beats a hand-maintained import list: a new model file
    is picked up without anyone remembering to register it.
    """
    package = importlib.import_module(_MODELS_PACKAGE)
    for module in pkgutil.walk_packages(package.__path__, prefix=f"{_MODELS_PACKAGE}."):
        importlib.import_module(module.name)


def target_metadata() -> MetaData:
    """Fully populated metadata, for Alembic and for schema creation in tests."""
    load_all_models()
    return metadata
