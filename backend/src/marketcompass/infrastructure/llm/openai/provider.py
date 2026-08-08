"""OpenAI-backed completion provider (parity with the Anthropic adapter).

Used when ``MC_LLM_PROVIDER=openai`` and a key is set. The ``openai`` SDK is
imported lazily so it is only required when selected. Anthropic is the primary
generative provider for this app; this exists so the ``LLMSettings`` contract's
third option is real rather than a stub.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from marketcompass.contexts.copilot.application.ports import LLMMessage, LLMResponse
from marketcompass.infrastructure.llm.base import LLMError

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam


class OpenAILLM:
    name = "openai"
    is_generative = True

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_output_tokens: int,
        request_timeout_seconds: float,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._timeout = request_timeout_seconds
        # Non-None for OpenAI-compatible endpoints such as OpenRouter, which
        # subclass this adapter rather than re-importing the SDK elsewhere.
        self._base_url = base_url
        self._default_headers = default_headers

    async def complete(self, *, system: str, messages: list[LLMMessage]) -> LLMResponse:
        try:
            import openai  # noqa: PLC0415 - lazy: only required when this provider runs
        except ImportError as exc:  # pragma: no cover - exercised only without the dep
            raise LLMError("the 'openai' package is not installed") from exc

        client = openai.AsyncOpenAI(
            api_key=self._api_key,
            timeout=self._timeout,
            base_url=self._base_url,
            default_headers=self._default_headers,
        )
        payload: list[dict[str, str]] = [{"role": "system", "content": system}]
        payload.extend({"role": m.role, "content": m.content} for m in messages)
        try:
            response = await client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_output_tokens,
                messages=cast("list[ChatCompletionMessageParam]", payload),
            )
        except openai.OpenAIError as exc:
            raise LLMError(f"{self.name} completion failed: {exc}") from exc

        text = response.choices[0].message.content or ""
        return LLMResponse(text=text, provider=self.name, model=self._model)
