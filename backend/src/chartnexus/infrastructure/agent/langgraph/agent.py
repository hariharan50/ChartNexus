"""LangGraph implementation of copilot's ``AgentPort``.

A single ReAct agent (``create_react_agent``) over the read-only market-data
tools, driven with Claude. It streams LangGraph events and translates them into
the copilot ``AgentEvent`` vocabulary the SSE transport already speaks — so the
endpoint and the whole frontend are unchanged.

Built per request in the copilot dependency with the tenant's market/options
services; ``run`` binds the tools to the tenant for that turn.

Observability: LangChain/LangGraph emit traces to LangSmith automatically when
``LANGSMITH_TRACING=true`` and ``LANGSMITH_API_KEY`` are set in the environment —
no code here. Leave both unset in production unless you intend to ship prompts
and tool I/O to LangSmith.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from chartnexus.contexts.copilot.application.ports import (
    AgentDone,
    AgentEvent,
    SkillsSelected,
    TextDelta,
    ToolFinished,
    ToolStarted,
    Turn,
)
from chartnexus.contexts.copilot.domain import compliance, persona, skills
from chartnexus.contexts.market_data.api.dependencies import MarketServices
from chartnexus.contexts.options_analytics.api.dependencies import OptionsAnalyticsServices
from chartnexus.infrastructure.agent.langgraph.planner import select_skills
from chartnexus.infrastructure.agent.langgraph.tools import build_agent_tools
from chartnexus.shared_kernel.types.identifiers import TenantId

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

# Friendly titles for the tool chips the UI renders. Falls back to a generic
# label so a new tool never breaks the surface.
_TOOL_TITLES: dict[str, str] = {
    "get_spot": "Checking spot",
    "get_futures": "Checking futures",
    "get_ohlc": "Reading price action",
    "get_previous_day_ohlc": "Reading prior session",
    "get_option_chain_summary": "Reading the option chain",
    "get_max_pain_and_pcr": "Reading OI & max pain",
    "get_gamma_exposure": "Reading dealer gamma",
    "get_indicators": "Computing indicators",
    "get_market_status": "Checking market status",
}

# Ceiling on graph super-steps (each model turn and each tool batch is one),
# so a misbehaving model cannot loop forever. A broad "analyse everything"
# question selects all skills and can call ~9 tools one at a time — that alone is
# ~19 super-steps — so this must clear that with headroom, not the langgraph
# default of 25 minus our earlier 12.
_RECURSION_LIMIT = 40


class LangGraphAgent:
    def __init__(
        self,
        *,
        model: BaseChatModel | None,
        market: MarketServices,
        options: OptionsAnalyticsServices,
        disclaimer: bool = True,
    ) -> None:
        self._model = model
        self._market = market
        self._options = options
        self._disclaimer = disclaimer

    @property
    def available(self) -> bool:
        return self._model is not None

    async def run(
        self,
        tenant_id: TenantId,
        symbol: str,
        question: str,
        history: list[Turn],
    ) -> AsyncIterator[AgentEvent]:
        if self._model is None:  # transport should have gated on `available`
            raise RuntimeError("agent is not available: no model configured")

        # Imported here so the optional 'agent' extra is only required when the
        # agent actually runs.
        from langchain_core.messages import AIMessage, HumanMessage  # noqa: PLC0415
        from langgraph.errors import GraphRecursionError  # noqa: PLC0415

        # `create_react_agent` is the prebuilt ReAct loop for our langgraph 1.x.
        # It is slated to move to `langchain.agents.create_agent` in langgraph
        # 2.0; swap the import when the `langchain` umbrella is added.
        from langgraph.prebuilt import create_react_agent  # noqa: PLC0415

        # Plan: pick the skills this question needs, then scope the executor to
        # only their tools and instructions.
        selected = await select_skills(self._model, question, history)
        yield SkillsSelected(titles=tuple(skills.titles_for(selected)))

        allowed = skills.tools_for(selected)
        tools = [
            t
            for t in build_agent_tools(tenant_id, self._market, self._options)
            if t.name in allowed
        ]
        system = persona.compose_system(
            skills.titles_for(selected), skills.instructions_block(selected)
        )
        graph = create_react_agent(self._model, tools, prompt=system)

        messages: list[Any] = []
        for turn in history:
            messages.append(
                HumanMessage(content=turn.text)
                if turn.role == "user"
                else AIMessage(content=turn.text)
            )
        # Tell Hella which instrument the user is looking at, so a bare "what's
        # the call?" reads against the right index without her having to ask.
        messages.append(HumanMessage(content=f"[Instrument in view: {symbol}]\n{question}"))

        answer_parts: list[str] = []
        try:
            async for event in graph.astream_events(
                {"messages": messages},
                version="v2",
                config={"recursion_limit": _RECURSION_LIMIT},
            ):
                kind = event.get("event")
                if kind == "on_chat_model_stream":
                    text = _delta_text(event)
                    if text:
                        answer_parts.append(text)
                        yield TextDelta(text=text)
                elif kind == "on_tool_start":
                    name = event.get("name", "")
                    yield ToolStarted(name=name, title=_TOOL_TITLES.get(name, "Working"))
                elif kind == "on_tool_end":
                    yield ToolFinished(name=event.get("name", ""))
        except GraphRecursionError:
            # The question needed more tool round-trips than the budget allows —
            # usually an "analyse everything" ask. Return a graceful nudge rather
            # than a dead-end error, keeping any partial text already streamed.
            if not answer_parts:
                nudge = (
                    "That's a lot to weigh in one pass. Ask me about one angle at a time — "
                    "the OI and options flow, the technical picture, the key levels, or a "
                    "specific setup — and I'll go deeper on it."
                )
                yield TextDelta(text=nudge)
                answer_parts.append(nudge)

        answer = "".join(answer_parts).strip()
        # Compliance guardrail: an analytical turn carries the "not advice"
        # framing even if the model omitted it. Streamed as a final chunk so the
        # UI and the saved transcript both include it. Disabled via
        # CN_LLM_AGENT_DISCLAIMER=false (e.g. while testing).
        if (
            self._disclaimer
            and skills.is_analytical(selected)
            and compliance.needs_disclaimer(answer)
        ):
            tail = f"\n\n{compliance.DISCLAIMER}"
            yield TextDelta(text=tail)
            answer = f"{answer}{tail}"

        yield AgentDone(text=answer)


def _delta_text(event: Any) -> str:
    """Pull user-facing text from an on_chat_model_stream event.

    A chunk's ``content`` is either a plain string or a list of content blocks
    (Anthropic returns blocks when thinking/tool-use interleave); we take only
    the text, ignoring thinking and tool-call deltas.
    """
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
