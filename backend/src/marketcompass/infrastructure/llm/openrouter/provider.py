"""OpenRouter-backed completion provider.

OpenRouter speaks the OpenAI wire protocol, so this is simply the OpenAI adapter
pointed at OpenRouter's ``base_url``. It *subclasses* ``OpenAILLM`` on purpose:
the ``import openai`` stays confined to the ``openai`` adapter package (enforced
by ``tests/architecture/test_vendor_imports``), so this module imports only
first-party code and never the vendor SDK directly.

Used when ``MC_LLM_PROVIDER=openrouter`` and a key is set. Model IDs are
namespaced (e.g. ``anthropic/claude-3.7-sonnet``, ``openai/gpt-4o``) — see
``LLMSettings.openrouter_model``.
"""

from __future__ import annotations

from marketcompass.infrastructure.llm.openai.provider import OpenAILLM

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterLLM(OpenAILLM):
    name = "openrouter"
    # is_generative is inherited from OpenAILLM (True).
