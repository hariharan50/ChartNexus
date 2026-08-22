"""Value objects for a user's AI (LLM) settings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from marketcompass.contexts.ai_settings.domain.errors import (
    ApiKeyInvalidError,
    ModelInvalidError,
    ProviderUnsupportedError,
)


class LlmProvider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OPENROUTER = "openrouter"


# Only Anthropic is wired into ``build_chat_model`` today. The other members are
# stored-and-validated shapes reserved for a fast follow; selecting one is
# rejected here so a user can never save a key we cannot actually run against a
# model.
SUPPORTED_PROVIDERS = frozenset({LlmProvider.ANTHROPIC})

# API keys vary by provider (``sk-ant-…``, ``sk-…``); bound loosely rather than
# by pattern so a new provider's format does not need a code change.
_MIN_KEY_LENGTH = 8
_MAX_KEY_LENGTH = 512
_MAX_MODEL_LENGTH = 128


@dataclass(frozen=True, slots=True)
class LlmCredentials:
    """A user's own LLM API application: provider, secret key, and model.

    The key never leaves the server after it is stored, and never appears in a
    repr or log line.
    """

    provider: LlmProvider
    api_key: str
    model: str

    def __post_init__(self) -> None:
        if self.provider not in SUPPORTED_PROVIDERS:
            raise ProviderUnsupportedError(self.provider.value)

        length = len(self.api_key)
        if not (_MIN_KEY_LENGTH <= length <= _MAX_KEY_LENGTH):
            raise ApiKeyInvalidError(
                f"The API key must be between {_MIN_KEY_LENGTH} and {_MAX_KEY_LENGTH} characters."
            )
        if any(character in self.api_key for character in "\r\n"):
            raise ApiKeyInvalidError("The API key must not contain line breaks.")
        if not self.api_key.isprintable():
            raise ApiKeyInvalidError("The API key contains unsupported characters.")

        if not (1 <= len(self.model) <= _MAX_MODEL_LENGTH):
            raise ModelInvalidError(
                f"The model must be between 1 and {_MAX_MODEL_LENGTH} characters."
            )

    @classmethod
    def parse(cls, provider: str, api_key: str, model: str) -> LlmCredentials:
        """Normalise then validate untrusted input from the settings form."""
        return cls(
            provider=_parse_provider(provider),
            api_key=(api_key or "").strip(),
            model=(model or "").strip(),
        )

    def __repr__(self) -> str:
        return (
            f"LlmCredentials(provider={self.provider.value!r}, model={self.model!r}, api_key=***)"
        )


def _parse_provider(value: str) -> LlmProvider:
    try:
        return LlmProvider((value or "").strip().lower())
    except ValueError as exc:
        raise ProviderUnsupportedError(value) from exc
