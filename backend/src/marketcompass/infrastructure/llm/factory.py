"""Pick an LLM provider from configuration, degrading safely.

Selection follows ``MC_LLM_PROVIDER`` but never *fails* over a misconfiguration:
a generative provider with no API key, or whose SDK isn't installed, falls back
to the rule-based provider so the app stays up. The app is therefore always
runnable, and only *upgrades* to Claude/OpenAI when a key and package are present.

Takes primitives rather than the settings object so ``infrastructure`` need not
import the composition root.
"""

from __future__ import annotations

from importlib.util import find_spec

from marketcompass.contexts.copilot.application.ports import LLMPort
from marketcompass.infrastructure.llm.rule_based.provider import RuleBasedLLM


def build_llm(
    *,
    provider: str,
    anthropic_api_key: str,
    openai_api_key: str,
    openrouter_api_key: str,
    openrouter_base_url: str,
    openrouter_headers: dict[str, str],
    model: str,
    max_output_tokens: int,
    request_timeout_seconds: float,
) -> LLMPort:
    if provider == "anthropic" and anthropic_api_key and find_spec("anthropic") is not None:
        from marketcompass.infrastructure.llm.anthropic.provider import (  # noqa: PLC0415
            AnthropicLLM,
        )

        return AnthropicLLM(
            api_key=anthropic_api_key,
            model=model,
            max_output_tokens=max_output_tokens,
            request_timeout_seconds=request_timeout_seconds,
        )

    if provider == "openai" and openai_api_key and find_spec("openai") is not None:
        from marketcompass.infrastructure.llm.openai.provider import OpenAILLM  # noqa: PLC0415

        return OpenAILLM(
            api_key=openai_api_key,
            model=model,
            max_output_tokens=max_output_tokens,
            request_timeout_seconds=request_timeout_seconds,
        )

    # OpenRouter rides the openai SDK, so it gates on that package being present.
    if provider == "openrouter" and openrouter_api_key and find_spec("openai") is not None:
        from marketcompass.infrastructure.llm.openrouter.provider import (  # noqa: PLC0415
            OpenRouterLLM,
        )

        return OpenRouterLLM(
            api_key=openrouter_api_key,
            model=model,
            max_output_tokens=max_output_tokens,
            request_timeout_seconds=request_timeout_seconds,
            base_url=openrouter_base_url,
            default_headers=openrouter_headers or None,
        )

    return RuleBasedLLM()
