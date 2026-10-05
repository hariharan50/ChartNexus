"""Domain errors for a user's AI (LLM) settings.

Each subclasses the shared ``ValidationError`` and carries a stable ``code`` the
frontend can branch on, plus the ``field`` the message belongs to so the form can
highlight the right input.
"""

from __future__ import annotations

from chartnexus.shared_kernel.domain.errors import ValidationError


class ProviderUnsupportedError(ValidationError):
    """The chosen provider is not one we can actually run yet.

    Only Anthropic is wired into the chat-model factory at launch; picking
    anything else must fail here rather than being stored as a key we can never
    use.
    """

    code = "llm_provider_unsupported"

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"The provider {provider!r} is not available yet. Choose Claude (Anthropic).",
            field="provider",
        )


class ApiKeyInvalidError(ValidationError):
    code = "llm_api_key_invalid"

    def __init__(self, message: str) -> None:
        super().__init__(message, field="api_key")


class ModelInvalidError(ValidationError):
    code = "llm_model_invalid"

    def __init__(self, message: str) -> None:
        super().__init__(message, field="model")
