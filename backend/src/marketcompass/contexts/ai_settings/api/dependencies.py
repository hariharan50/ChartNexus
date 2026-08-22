"""Per-request assembly for the AI-settings routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.ai_settings.application.use_cases import (
    ClearApiKey,
    GetAiSettings,
    SaveAiSettings,
)
from marketcompass.infrastructure.persistence.postgresql.repositories.settings.ai_settings_repository import (
    SqlAlchemyAiSettingsRepository,
)
from marketcompass.infrastructure.time.clock import SystemClock
from marketcompass.infrastructure.transport.http.dependencies import (
    SessionUnitOfWork,
    get_container,
    get_session,
)


@dataclass(slots=True)
class AiSettingsServices:
    get: GetAiSettings
    save: SaveAiSettings
    clear: ClearApiKey


def build_ai_settings_services(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AiSettingsServices:
    container = get_container(request)
    clock = SystemClock()

    repository = SqlAlchemyAiSettingsRepository(session, container.ai_settings_cipher)
    uow = SessionUnitOfWork(session)

    return AiSettingsServices(
        get=GetAiSettings(repository=repository),
        save=SaveAiSettings(repository=repository, clock=clock, uow=uow),
        clear=ClearApiKey(repository=repository, clock=clock, uow=uow),
    )


Services = Annotated[AiSettingsServices, Depends(build_ai_settings_services)]
