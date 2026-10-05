"""STRYX's intent router: is this a setup request, or just talk?

One cheap structured LLM call (mirroring copilot's planner) decides whether the
message wants a trade scan — a [STRYX CALL] over the live market — or is plain
conversation (a greeting, "who are you?", a general question, thanks, banter).
The adapter then runs the matching mode: the full tool-calling scan, or a short
friendly reply with no tools and no template.

Degrades safely: any failure falls back to ``scan`` so STRYX's primary job (the
call) is never blocked by a router hiccup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from chartnexus.contexts.stryx.application.ports import Turn

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

Intent = Literal["scan", "conversation"]

# How many recent turns to show the router, so a follow-up like "and why?" is
# classified against what was just being discussed.
_HISTORY_WINDOW = 4


class _IntentPlan(BaseModel):
    intent: Intent = Field(
        description=(
            "'scan' when the user wants a trade setup / call / entry / read of the market "
            "right now (e.g. 'any setup?', 'where's the breakout?', 'scan NIFTY', 'is there "
            "an edge?', 'what's the call?'). 'conversation' for a greeting, asking who you "
            "are, thanks, banter, or a general/how-does-this-work question that does not ask "
            "for a live market read."
        )
    )


async def classify_intent(model: BaseChatModel, question: str, history: list[Turn]) -> Intent:
    prompt = (
        "You route a message sent to STRYX, an aggressive options trade-call agent.\n"
        "Decide if it wants a trade scan ('scan') or is just conversation "
        "('conversation').\n\n"
        f"{_recent(history)}"
        f"Message: {question}\n\n"
        "Return the intent."
    )
    try:
        # `with_structured_output` can itself raise on an unsupported model, so it
        # is inside the guard with the call.
        router = model.with_structured_output(_IntentPlan)
        plan = await router.ainvoke(prompt)
    except Exception:  # a router failure must not block the call
        return "scan"

    return plan.intent if isinstance(plan, _IntentPlan) else "scan"


def _recent(history: list[Turn]) -> str:
    if not history:
        return ""
    lines = [f"{turn.role}: {turn.text}" for turn in history[-_HISTORY_WINDOW:]]
    return "Recent conversation:\n" + "\n".join(lines) + "\n\n"
