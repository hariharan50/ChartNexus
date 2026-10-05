"""AI-settings endpoints.

Every route is authenticated and scoped to the caller's own user. The user's LLM
provider, API key, and model live here; the agents (HELLA, STRYX) read them per
request, so saving a key turns the AI Console on and removing it turns it off.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from chartnexus.contexts.ai_settings.api.dependencies import Services
from chartnexus.contexts.ai_settings.api.schemas import (
    AiSettingsResponse,
    SaveAiSettingsRequest,
)
from chartnexus.contexts.ai_settings.application.use_cases import SaveAiSettingsCommand
from chartnexus.infrastructure.transport.http.dependencies import CurrentPrincipal

router = APIRouter(prefix="/ai/settings", tags=["ai-settings"])


@router.get(
    "",
    response_model=AiSettingsResponse,
    summary="Current user's AI settings",
    description="Returns the saved provider and model, and the API key masked. Never the raw key.",
)
async def get_settings(principal: CurrentPrincipal, services: Services) -> AiSettingsResponse:
    view = await services.get(principal.user_id)
    return AiSettingsResponse.of(view)


@router.put(
    "",
    response_model=AiSettingsResponse,
    status_code=status.HTTP_200_OK,
    summary="Save the user's LLM provider, API key, and model",
    responses={422: {"description": "The provider, key, or model is invalid"}},
)
async def save_settings(
    payload: SaveAiSettingsRequest,
    principal: CurrentPrincipal,
    services: Services,
) -> AiSettingsResponse:
    view = await services.save(
        SaveAiSettingsCommand(
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
            provider=payload.provider,
            api_key=payload.api_key,
            model=payload.model,
        )
    )
    return AiSettingsResponse.of(view)


@router.delete(
    "/key",
    response_model=AiSettingsResponse,
    summary="Remove the stored API key, disabling the agents",
)
async def clear_key(principal: CurrentPrincipal, services: Services) -> AiSettingsResponse:
    view = await services.clear(principal.user_id)
    return AiSettingsResponse.of(view)
