"""Per-request assembly for the instrument-catalog routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.instrument_catalog.application.use_cases import (
    GetInstrument,
    ListInstruments,
)
from marketcompass.infrastructure.persistence.postgresql.repositories.instrument_catalog.instrument_repository import (
    SqlAlchemyInstrumentRepository,
)
from marketcompass.infrastructure.transport.http.dependencies import get_session


@dataclass(slots=True)
class InstrumentCatalogServices:
    search: ListInstruments
    get: GetInstrument


def build_instrument_catalog_services(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InstrumentCatalogServices:
    repository = SqlAlchemyInstrumentRepository(session)
    return InstrumentCatalogServices(
        search=ListInstruments(repository=repository),
        get=GetInstrument(repository=repository),
    )


Services = Annotated[InstrumentCatalogServices, Depends(build_instrument_catalog_services)]
