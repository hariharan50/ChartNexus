"""Per-request assembly for the copilot chat routes.

The guidance bridge and the LLM factory both live in ``infrastructure``, so this
module never imports ``signals`` or a provider SDK directly — it only reads the
LLM configuration off the container and wires the ``Converse`` use case.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.copilot.application.converse import Converse
from marketcompass.infrastructure.brokers.copilot_guidance_source import (
    build_copilot_guidance_source,
)
from marketcompass.infrastructure.llm.factory import build_llm
from marketcompass.infrastructure.transport.http.dependencies import (
    get_container,
    get_session,
)


@dataclass(slots=True)
class CopilotServices:
    converse: Converse


def build_copilot_services(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CopilotServices:
    container = get_container(request)
    llm_settings = container.settings.llm
    llm = build_llm(
        provider=llm_settings.provider,
        anthropic_api_key=llm_settings.anthropic_api_key.get_secret_value(),
        openai_api_key=llm_settings.openai_api_key.get_secret_value(),
        openrouter_api_key=llm_settings.openrouter_api_key.get_secret_value(),
        openrouter_base_url=llm_settings.openrouter_base_url,
        openrouter_headers=llm_settings.openrouter_headers,
        model=llm_settings.resolved_model,
        max_output_tokens=llm_settings.max_output_tokens,
        request_timeout_seconds=llm_settings.request_timeout_seconds,
    )
    guidance = build_copilot_guidance_source(request, session)
    return CopilotServices(converse=Converse(guidance=guidance, llm=llm))


Services = Annotated[CopilotServices, Depends(build_copilot_services)]
