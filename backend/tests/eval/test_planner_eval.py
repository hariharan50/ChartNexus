"""LLM-backed eval: does the planner route questions to the right skill?

This calls the real model, so it is gated: skipped unless the ``agent`` extra is
installed AND ``MC_LLM_ANTHROPIC_API_KEY`` is set. It is not part of the default
test run (see the Taskfile / pytest markers) — run it on demand to catch skill-
selection regressions after prompt or registry changes:

    MC_LLM_ANTHROPIC_API_KEY=sk-ant-... uv run --extra agent pytest tests/eval -m eval

Each case asserts the expected skill is *among* the planner's selection (it may
legitimately pick more than one), which is the property the executor relies on.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("langchain_anthropic")

from marketcompass.contexts.copilot.domain import skills
from marketcompass.infrastructure.agent.langgraph.llm import build_chat_model
from marketcompass.infrastructure.agent.langgraph.planner import select_skills

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.getenv("MC_LLM_ANTHROPIC_API_KEY"),
        reason="MC_LLM_ANTHROPIC_API_KEY not set — the planner eval calls the real model",
    ),
    pytest.mark.filterwarnings("ignore::DeprecationWarning"),
]

_CASES = [
    ("What is open interest telling us about NIFTY?", "oi_options_flow"),
    ("Is NIFTY overbought on the charts right now?", "price_action_technical"),
    ("What are the key levels for NIFTY today?", "levels_range"),
    ("If I were long NIFTY, where would a sensible stop sit?", "trade_setup_risk"),
    ("Is the market open right now?", "market_context"),
    ("Hi, who are you?", "conversational"),
]


def _model():
    return build_chat_model(
        provider="anthropic",
        api_key=os.environ["MC_LLM_ANTHROPIC_API_KEY"],
        model=os.getenv("MC_LLM_MODEL", "claude-sonnet-5"),
        max_output_tokens=512,
        request_timeout_seconds=30.0,
    )


@pytest.mark.parametrize(("question", "expected"), _CASES)
async def test_planner_selects_expected_skill(question: str, expected: str) -> None:
    model = _model()
    assert model is not None, "build_chat_model returned None despite a key"

    selected = await select_skills(model, question, [])

    assert set(selected) <= set(skills.skill_ids()), selected
    assert expected in selected, f"{question!r} -> {selected}, expected {expected!r} among them"
