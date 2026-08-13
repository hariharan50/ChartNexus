"""The chat model behind the agent.

Phase A is Claude-only: the agent runs on ``ChatAnthropic`` when
``MC_LLM_PROVIDER=anthropic`` and a key is set. Returns ``None`` when no model is
configured (or ``langchain-anthropic`` isn't installed) — the console is LLM-only,
so ``None`` disables the tab rather than degrading. Other providers are a later
phase; they slot in here behind the same return type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


def build_chat_model(
    *,
    provider: str,
    api_key: str,
    model: str,
    max_output_tokens: int,
    request_timeout_seconds: float,
) -> BaseChatModel | None:
    if provider != "anthropic" or not api_key:
        return None
    try:
        from langchain_anthropic import ChatAnthropic  # noqa: PLC0415 - lazy, optional extra
    except ImportError:  # pragma: no cover - exercised only without the 'agent' extra
        return None

    return ChatAnthropic(
        model=model,  # 'model' is an alias for model_name
        api_key=api_key,
        max_tokens=max_output_tokens,  # alias for max_tokens_to_sample
        timeout=request_timeout_seconds,  # alias for default_request_timeout
    )
