"""LlmCredentials validation — the rules that guard what can be saved."""

from __future__ import annotations

import pytest

from chartnexus.contexts.ai_settings.domain.errors import (
    ApiKeyInvalidError,
    ModelInvalidError,
    ProviderUnsupportedError,
)
from chartnexus.contexts.ai_settings.domain.value_objects import (
    SUPPORTED_PROVIDERS,
    LlmCredentials,
    LlmProvider,
)

pytestmark = pytest.mark.unit

KEY = "sk-ant-example-key-value"


def test_parses_and_normalises() -> None:
    creds = LlmCredentials.parse("  ANTHROPIC ", f"  {KEY}  ", "  claude-sonnet-5 ")
    assert creds.provider is LlmProvider.ANTHROPIC
    assert creds.api_key == KEY
    assert creds.model == "claude-sonnet-5"


def test_only_supported_providers_are_accepted() -> None:
    # Guards against saving a key we cannot actually run a model with today.
    assert LlmProvider.ANTHROPIC in SUPPORTED_PROVIDERS
    for provider in ("openai", "openrouter"):
        with pytest.raises(ProviderUnsupportedError):
            LlmCredentials.parse(provider, KEY, "some-model")


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ProviderUnsupportedError):
        LlmCredentials.parse("gemini", KEY, "some-model")


@pytest.mark.parametrize("key", ["short", "", "x" * 513])
def test_key_length_is_bounded(key: str) -> None:
    with pytest.raises(ApiKeyInvalidError):
        LlmCredentials.parse("anthropic", key, "claude-sonnet-5")


@pytest.mark.parametrize("key", ["line\nbreak-in-key-value", "tab\tis-not-printable-\x00"])
def test_unprintable_or_multiline_keys_are_rejected(key: str) -> None:
    with pytest.raises(ApiKeyInvalidError):
        LlmCredentials.parse("anthropic", key, "claude-sonnet-5")


@pytest.mark.parametrize("model", ["", "x" * 129])
def test_model_length_is_bounded(model: str) -> None:
    with pytest.raises(ModelInvalidError):
        LlmCredentials.parse("anthropic", KEY, model)


def test_repr_never_leaks_the_key() -> None:
    creds = LlmCredentials.parse("anthropic", KEY, "claude-sonnet-5")
    assert KEY not in repr(creds)
    assert "api_key=***" in repr(creds)
