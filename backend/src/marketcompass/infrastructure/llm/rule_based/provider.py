"""The keyless default provider.

It is deliberately not generative: ``is_generative`` is ``False``, so the copilot
conversation layer answers deterministically from the structured guidance and
never calls ``complete``. This is what makes the whole app run with no API key —
the same posture the README documents for ``MC_LLM_PROVIDER=rule_based``.
"""

from __future__ import annotations

from marketcompass.contexts.copilot.application.ports import LLMMessage, LLMResponse


class RuleBasedLLM:
    name = "rule_based"
    is_generative = False

    async def complete(self, *, system: str, messages: list[LLMMessage]) -> LLMResponse:  # noqa: ARG002
        # Never reached in normal flow (the conversation layer checks
        # ``is_generative`` first), but implemented so the type is a full LLMPort:
        # echo the last user message so a mis-wired caller degrades to a no-op
        # rather than crashing.
        last = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return LLMResponse(text=last, provider=self.name, model=None)
