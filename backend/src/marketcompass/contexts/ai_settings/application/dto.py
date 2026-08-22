"""Data crossing the AI-settings application boundary.

Nothing here may carry the raw API key. The view a caller receives is the same
view that can safely be logged: the key is only ever present masked.
"""

from __future__ import annotations

from dataclasses import dataclass

from marketcompass.contexts.ai_settings.domain.aggregate import AiSettings

# What a brand-new user sees before they have saved anything. Mirrors the default
# the settings form pre-selects.
_DEFAULT_PROVIDER = "anthropic"
_DEFAULT_MODEL = "claude-sonnet-5"


@dataclass(frozen=True, slots=True)
class AiSettingsView:
    provider: str
    model: str
    configured: bool
    """A key is stored, so the agent tabs can run."""

    available: bool
    """Stored *and* on a provider we can actually run (Anthropic today)."""

    masked_api_key: str | None

    @classmethod
    def of(cls, settings: AiSettings | None) -> AiSettingsView:
        if settings is None:
            return cls(
                provider=_DEFAULT_PROVIDER,
                model=_DEFAULT_MODEL,
                configured=False,
                available=False,
                masked_api_key=None,
            )
        return cls(
            provider=settings.provider.value,
            model=settings.model,
            configured=settings.configured,
            available=settings.available,
            masked_api_key=settings.masked_api_key,
        )
