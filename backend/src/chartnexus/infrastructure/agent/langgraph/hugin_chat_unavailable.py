"""HUGIN chat when no model is configured — import-safe without the extra.

``HuginChatAgent`` imports LangGraph at call time, so the builder returns *this*
when the user has no usable key, letting availability answer without the LangChain
stack. The transport gates on ``available`` and returns 503 before ``stream`` is
called; the generator is empty rather than raising so a stray call degrades to "no
answer".
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from chartnexus.contexts.hugin.domain.conversation import ChatEvent, Turn


class UnavailableHuginChat:
    available = False

    async def stream(
        self, digest: str, question: str, history: list[Turn]
    ) -> AsyncIterator[ChatEvent]:
        _ = (digest, question, history)
        empty: tuple[ChatEvent, ...] = ()
        for event in empty:  # pragma: no cover
            yield event
