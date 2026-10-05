"""Wire contract for AI-settings endpoints.

The request model accepts a raw API key; no response model has a field that could
hold one. The key is only ever returned masked.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from chartnexus.contexts.ai_settings.application.dto import AiSettingsView


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SaveAiSettingsRequest(_Schema):
    provider: str = Field(
        examples=["anthropic"],
        description="LLM provider. Only 'anthropic' is available today.",
    )
    api_key: str = Field(
        min_length=8,
        max_length=512,
        description="Your own LLM API key. Stored encrypted and never returned.",
    )
    model: str = Field(
        min_length=1,
        max_length=128,
        examples=["claude-sonnet-5"],
        description="The model ID to run for this provider.",
    )


class AiSettingsResponse(_Schema):
    provider: str
    model: str
    configured: bool
    available: bool
    masked_api_key: str | None

    @classmethod
    def of(cls, view: AiSettingsView) -> AiSettingsResponse:
        return cls(
            provider=view.provider,
            model=view.model,
            configured=view.configured,
            available=view.available,
            masked_api_key=view.masked_api_key,
        )
