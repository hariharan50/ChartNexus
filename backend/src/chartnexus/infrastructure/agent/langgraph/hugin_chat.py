"""LangGraph/Claude implementation of HUGIN's ``ChatPort``.

Memory-grounded chat: the model is given HUGIN's persona + memory digest as the
system prompt and answers with **no tools bound** — HUGIN reasons over what it has
already observed and learned, not the live market. Streams token deltas via
``astream_events``, the same transport shape as HELLA/STRYX minus tool events.

Separate from the other agents' adapters (the contexts stay isolated); only the
chat-model builder is shared. The small streaming helpers are duplicated rather
than imported from the stryx adapter to keep the two independent.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from chartnexus.contexts.hugin.domain import persona
from chartnexus.contexts.hugin.domain.conversation import ChatDone, ChatEvent, TextDelta, Turn

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


class HuginChatAgent:
    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    @property
    def available(self) -> bool:
        return True

    async def stream(
        self, digest: str, question: str, history: list[Turn]
    ) -> AsyncIterator[ChatEvent]:
        from langgraph.prebuilt import create_react_agent  # noqa: PLC0415

        system = f"{persona.compose_chat_system()}\n\n{digest}"
        graph = create_react_agent(self._model, [], prompt=system)

        messages = _history_messages(history)
        messages.append(_human(question))

        parts: list[str] = []
        async for event in graph.astream_events({"messages": messages}, version="v2"):
            if event.get("event") == "on_chat_model_stream":
                text = _delta_text(event)
                if text:
                    parts.append(text)
                    yield TextDelta(text=text)
        yield ChatDone(text="".join(parts).strip())


def _history_messages(history: list[Turn]) -> list[Any]:
    from langchain_core.messages import AIMessage, HumanMessage  # noqa: PLC0415

    return [
        HumanMessage(content=turn.text) if turn.role == "user" else AIMessage(content=turn.text)
        for turn in history
    ]


def _human(text: str) -> Any:
    from langchain_core.messages import HumanMessage  # noqa: PLC0415

    return HumanMessage(content=text)


def _delta_text(event: Any) -> str:
    chunk = event.get("data", {}).get("chunk")
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""
