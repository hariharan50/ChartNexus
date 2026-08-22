"""AI-settings use cases: read, save, and clear a user's LLM configuration."""

from __future__ import annotations

from dataclasses import dataclass

from marketcompass.contexts.ai_settings.application.dto import AiSettingsView
from marketcompass.contexts.ai_settings.application.ports import (
    AiSettingsRepository,
    Clock,
    UnitOfWork,
)
from marketcompass.contexts.ai_settings.domain.aggregate import AiSettings
from marketcompass.contexts.ai_settings.domain.value_objects import LlmCredentials
from marketcompass.shared_kernel.types.identifiers import TenantId, UserId


@dataclass(frozen=True, slots=True)
class SaveAiSettingsCommand:
    user_id: UserId
    tenant_id: TenantId
    provider: str
    api_key: str
    model: str


@dataclass(frozen=True, slots=True)
class GetAiSettings:
    repository: AiSettingsRepository

    async def __call__(self, user_id: UserId) -> AiSettingsView:
        return AiSettingsView.of(await self.repository.find(user_id))


@dataclass(frozen=True, slots=True)
class SaveAiSettings:
    repository: AiSettingsRepository
    clock: Clock
    uow: UnitOfWork

    async def __call__(self, command: SaveAiSettingsCommand) -> AiSettingsView:
        # Validation (provider supported, key/model bounds) happens in the value
        # object, before anything touches the database.
        credentials = LlmCredentials.parse(command.provider, command.api_key, command.model)
        now = self.clock.now()

        settings = await self.repository.find(command.user_id)
        if settings is None:
            settings = AiSettings.create(
                user_id=command.user_id,
                tenant_id=command.tenant_id,
                credentials=credentials,
                now=now,
            )
        else:
            settings.update_credentials(credentials, now)

        await self.repository.upsert(settings)
        await self.uow.commit()
        return AiSettingsView.of(settings)


@dataclass(frozen=True, slots=True)
class ClearApiKey:
    repository: AiSettingsRepository
    clock: Clock
    uow: UnitOfWork

    async def __call__(self, user_id: UserId) -> AiSettingsView:
        settings = await self.repository.find(user_id)
        if settings is None:
            # Nothing to clear — idempotent.
            return AiSettingsView.of(None)
        settings.clear_key(self.clock.now())
        await self.repository.upsert(settings)
        await self.uow.commit()
        return AiSettingsView.of(settings)
