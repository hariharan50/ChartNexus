"""Provider selection for the copilot LLM, with OpenRouter as a 4th option.

The factory must never *fail* over misconfiguration: a generative provider with
no key (or no SDK) falls back to the keyless rule-based provider so the app stays
up. OpenRouter rides the openai SDK and lives behind the openai adapter, so its
selection is gated the same way.
"""

from __future__ import annotations

from importlib.util import find_spec

import pytest

from marketcompass.bootstrap.settings import LLMSettings
from marketcompass.infrastructure.llm.factory import build_llm
from marketcompass.infrastructure.llm.openrouter.provider import OpenRouterLLM
from marketcompass.infrastructure.llm.rule_based.provider import RuleBasedLLM

pytestmark = pytest.mark.unit


def _build(**overrides: object):  # type: ignore[no-untyped-def]
    kwargs: dict[str, object] = {
        "provider": "rule_based",
        "anthropic_api_key": "",
        "openai_api_key": "",
        "openrouter_api_key": "",
        "openrouter_base_url": "https://openrouter.ai/api/v1",
        "openrouter_headers": {},
        "model": "anthropic/claude-3.7-sonnet",
        "max_output_tokens": 2048,
        "request_timeout_seconds": 30.0,
    }
    kwargs.update(overrides)
    return build_llm(**kwargs)  # type: ignore[arg-type]


def test_openrouter_without_a_key_degrades_to_rule_based() -> None:
    llm = _build(provider="openrouter", openrouter_api_key="")
    assert isinstance(llm, RuleBasedLLM)
    assert llm.is_generative is False


def test_openrouter_provider_identity() -> None:
    # Constructing the provider must not require the openai SDK — the import is
    # lazy inside ``complete``.
    llm = OpenRouterLLM(
        api_key="sk-or-test",
        model="anthropic/claude-3.7-sonnet",
        max_output_tokens=2048,
        request_timeout_seconds=30.0,
        base_url="https://openrouter.ai/api/v1",
    )
    assert llm.name == "openrouter"
    assert llm.is_generative is True


@pytest.mark.skipif(find_spec("openai") is None, reason="openai SDK not installed")
def test_openrouter_with_a_key_selects_the_openrouter_provider() -> None:
    llm = _build(provider="openrouter", openrouter_api_key="sk-or-test")
    assert isinstance(llm, OpenRouterLLM)
    assert llm.name == "openrouter"


def test_resolved_model_uses_the_openrouter_field_only_for_openrouter() -> None:
    openrouter = LLMSettings(provider="openrouter", openrouter_model="openai/gpt-4o")
    assert openrouter.resolved_model == "openai/gpt-4o"

    anthropic = LLMSettings(provider="anthropic", model="claude-sonnet-5")
    assert anthropic.resolved_model == "claude-sonnet-5"


def test_openrouter_headers_include_only_the_values_that_are_set() -> None:
    both = LLMSettings(
        openrouter_site_url="https://mc.example", openrouter_app_name="MarketCompass"
    )
    assert both.openrouter_headers == {
        "HTTP-Referer": "https://mc.example",
        "X-Title": "MarketCompass",
    }

    assert LLMSettings().openrouter_headers == {}
