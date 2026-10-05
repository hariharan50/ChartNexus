"""The planner: pick the skills a question needs before the executor runs.

One structured LLM call maps the question (with a little conversation context)
onto skill ids from the registry. The executor is then scoped to only those
skills' tools and instructions — tighter context, better focus, lower cost.

Degrades safely: any failure or an empty/unknown selection falls back to the
registry's default analytical skills, so a planner hiccup never blocks an answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from chartnexus.contexts.copilot.application.ports import Turn
from chartnexus.contexts.copilot.domain import skills

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

# How many recent turns to show the planner, so a follow-up like "and the stop?"
# is classified against what was being discussed.
_HISTORY_WINDOW = 4


class _SkillPlan(BaseModel):
    skills: list[str] = Field(
        description=(
            "The ids of the skills needed to answer, chosen ONLY from the provided "
            "catalogue. Use 'conversational' for greetings/identity/help. Pick the "
            "smallest set that fully covers the question."
        )
    )


async def select_skills(model: BaseChatModel, question: str, history: list[Turn]) -> list[str]:
    prompt = (
        "You route a user's question to the analyst skills needed to answer it.\n"
        f"Catalogue (id: when to use):\n{skills.planner_catalogue()}\n\n"
        f"{_recent(history)}"
        f"Question: {question}\n\n"
        "Return the skill ids that apply."
    )
    try:
        # `with_structured_output` itself raises on a model that doesn't support
        # it, so it is inside the guard alongside the call.
        planner = model.with_structured_output(_SkillPlan)
        plan = await planner.ainvoke(prompt)
    except Exception:  # a planner failure must not block the answer
        return list(skills.DEFAULT_IDS)

    selected = skills.valid_ids(plan.skills) if isinstance(plan, _SkillPlan) else []
    return selected or list(skills.DEFAULT_IDS)


def _recent(history: list[Turn]) -> str:
    if not history:
        return ""
    lines = [f"{turn.role}: {turn.text}" for turn in history[-_HISTORY_WINDOW:]]
    return "Recent conversation:\n" + "\n".join(lines) + "\n\n"
