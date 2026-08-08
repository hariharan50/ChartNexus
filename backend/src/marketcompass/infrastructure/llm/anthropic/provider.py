"""Anthropic-backed completion provider.

Used when ``MC_LLM_PROVIDER=anthropic`` and an API key is set. The ``anthropic``
SDK is imported lazily so it is only a dependency when this provider is actually
selected — the rule-based default never touches it. Model, token cap, and timeout
all come from ``LLMSettings`` (``MC_LLM_MODEL`` etc.), so the deployment picks the
model, not this code.
"""

from __future__ import annotations

from marketcompass.contexts.copilot.application.ports import LLMMessage, LLMResponse
from marketcompass.infrastructure.llm.base import LLMError


class AnthropicLLM:
    name = "anthropic"
    is_generative = True

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_output_tokens: int,
        request_timeout_seconds: float,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._timeout = request_timeout_seconds

    async def complete(self, *, system: str, messages: list[LLMMessage]) -> LLMResponse:
        # Imported here so the package is only required when this provider runs.
        try:
            import anthropic  # noqa: PLC0415 - lazy: only required when this provider runs
        except ImportError as exc:  # pragma: no cover - exercised only without the dep
            raise LLMError("the 'anthropic' package is not installed") from exc

        client = anthropic.AsyncAnthropic(api_key=self._api_key, timeout=self._timeout)
        try:
            response = await client.messages.create(
                model=self._model,
                max_tokens=self._max_output_tokens,
                system=system,
                messages=[{"role": m.role, "content": m.content} for m in messages],
            )
        except anthropic.AnthropicError as exc:
            raise LLMError(f"anthropic completion failed: {exc}") from exc
        finally:
            await client.close()

        text = "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        )
        return LLMResponse(text=text, provider=self.name, model=self._model)
