"""MME100's intent router: is this an analysis request, or just talk?

One cheap structured LLM call (mirroring copilot's planner and STRYX's) decides
whether the message wants a market analysis — the six-section pre-market read — or
is plain conversation (a greeting, "who are you?", a general question, thanks). The
adapter then runs the matching mode: the full tool + web-search read, or a short
friendly reply.

Degrades safely: any failure falls back to ``analysis`` so MME100's primary job is
never blocked by a router hiccup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from chartnexus.contexts.mme100.application.ports import Turn

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

Intent = Literal["analysis", "conversation"]

# How many recent turns to show the router, so a follow-up like "and the risks?" is
# classified against what was just being discussed.
_HISTORY_WINDOW = 4


class _IntentPlan(BaseModel):
    intent: Intent = Field(
        description=(
            "'analysis' when the user wants a market read / pre-market outlook / levels / "
            "sector or stock view / global cues right now (e.g. 'pre-market outlook?', "
            "'key levels today?', 'what about banking?', 'analyse NIFTY'). 'conversation' "
            "for a greeting, asking who you are, thanks, banter, or a general/how-does-this-"
            "work question that does not ask for a market read."
        )
    )


async def classify_intent(model: BaseChatModel, question: str, history: list[Turn]) -> Intent:
    prompt = (
        "You route a message sent to MME100, an Indian pre-market analysis agent.\n"
        "Decide if it wants a market analysis ('analysis') or is just conversation "
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
    except Exception:  # a router failure must not block the analysis
        return "analysis"

    return plan.intent if isinstance(plan, _IntentPlan) else "analysis"


def _recent(history: list[Turn]) -> str:
    if not history:
        return ""
    lines = [f"{turn.role}: {turn.text}" for turn in history[-_HISTORY_WINDOW:]]
    return "Recent conversation:\n" + "\n".join(lines) + "\n\n"
