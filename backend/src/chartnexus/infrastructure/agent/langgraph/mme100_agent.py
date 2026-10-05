"""LangGraph implementation of MME100's ``AgentPort``.

A single ReAct agent (``create_react_agent``) over the same read-only India market
tools HELLA/STRYX read, PLUS Anthropic's server-side ``web_search`` tool for the
global cues the broker tools don't cover (US markets, GIFT Nifty, crude, USD-INR,
yields). Driven with Claude, with MME100's persona and its six-section
market-analysis skill folded into the system prompt.

Deliberately separate from HELLA's and STRYX's adapters rather than a shared
generic: the contexts stay isolated. The only reused pieces are the low-level,
domain-agnostic infra helpers — the tool builder and the chat-model builder.

Web search: the Anthropic built-in tool is a plain spec dict added to the tools
list alongside the client-side StructuredTools; ``langchain-anthropic`` binds it
and Anthropic runs it server-side. It is gated on ``web_search_max_uses`` so a
value of 0 cleanly disables it (the escape hatch if the built-in tool ever
misbehaves) without touching the analytical read of the India tools.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from chartnexus.contexts.market_data.api.dependencies import MarketServices
from chartnexus.contexts.mme100.application.ports import (
    AgentDone,
    AgentEvent,
    SkillsConsidered,
    TextDelta,
    ToolFinished,
    ToolStarted,
    Turn,
)
from chartnexus.contexts.mme100.domain import compliance, persona, skill
from chartnexus.contexts.options_analytics.api.dependencies import OptionsAnalyticsServices
from chartnexus.infrastructure.agent.langgraph.mme100_planner import classify_intent
from chartnexus.infrastructure.agent.langgraph.tools import build_agent_tools
from chartnexus.shared_kernel.types.identifiers import TenantId

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

# Friendly titles for the tool chips the UI renders.
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
    "web_search": "Searching global cues",
}

# The Anthropic built-in web search tool type. Stable string per the Anthropic
# tool-versioning scheme; bump only when Anthropic ships a new revision.
_WEB_SEARCH_TYPE = "web_search_20250305"

# MME100 pulls the full India surface plus several web searches in one analytical
# pass, so the ceiling must clear that with headroom.
_RECURSION_LIMIT = 50


class Mme100LangGraphAgent:
    def __init__(
        self,
        *,
        model: BaseChatModel | None,
        market: MarketServices,
        options: OptionsAnalyticsServices,
        disclaimer: bool = True,
        web_search_max_uses: int = 5,
    ) -> None:
        self._model = model
        self._market = market
        self._options = options
        self._disclaimer = disclaimer
        self._web_search_max_uses = web_search_max_uses

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
        model = self._model
        if model is None:  # transport should have gated on `available`
            raise RuntimeError("agent is not available: no model configured")

        # Route first: a real analysis request runs the six-section read; a greeting
        # or general question gets a friendly reply with no tools and no framework.
        intent = await classify_intent(model, question, history)
        if intent == "conversation":
            async for event in self._converse(model, question, history):
                yield event
            return

        async for event in self._analyse(model, tenant_id, symbol, question, history):
            yield event

    async def _converse(
        self, model: BaseChatModel, question: str, history: list[Turn]
    ) -> AsyncIterator[AgentEvent]:
        """Small talk: MME100 as a warm teammate — no tools, no framework."""
        from langgraph.prebuilt import create_react_agent  # noqa: PLC0415

        graph = create_react_agent(model, [], prompt=persona.compose_conversational())
        messages = self._history_messages(history)
        messages.append(_human(question))

        answer_parts: list[str] = []
        async for event in graph.astream_events({"messages": messages}, version="v2"):
            if event.get("event") == "on_chat_model_stream":
                text = _delta_text(event)
                if text:
                    answer_parts.append(text)
                    yield TextDelta(text=text)
        yield AgentDone(text="".join(answer_parts).strip())

    async def _analyse(
        self,
        model: BaseChatModel,
        tenant_id: TenantId,
        symbol: str,
        question: str,
        history: list[Turn],
    ) -> AsyncIterator[AgentEvent]:
        """The full six-section pre-market analysis over the India tools + web search."""
        from langgraph.errors import GraphRecursionError  # noqa: PLC0415
        from langgraph.prebuilt import create_react_agent  # noqa: PLC0415

        # Surface the six sections as chips so the UI shows the framework MME100
        # reasons through.
        yield SkillsConsidered(titles=skill.titles())

        allowed = set(skill.CORE_TOOLS)
        tools: list[Any] = [
            t
            for t in build_agent_tools(tenant_id, self._market, self._options)
            if t.name in allowed
        ]
        web_search = self._web_search_tool()
        if web_search is not None:
            tools.append(web_search)

        graph = create_react_agent(model, tools, prompt=persona.compose_analysis())

        messages = self._history_messages(history)
        messages.append(_human(f"[Instrument in view: {symbol}]\n{question}"))

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
            # Ran out of tool round-trips. Keep any partial text; add a short nudge
            # only when nothing streamed, rather than a dead-end error.
            if not answer_parts:
                nudge = (
                    "Couldn't complete the full read in time — too much to weigh in one "
                    "pass. Ask me about one instrument and I'll break it down."
                )
                yield TextDelta(text=nudge)
                answer_parts.append(nudge)

        answer = "".join(answer_parts).strip()
        # Compliance guardrail: every analysis carries the educational framing even
        # if the model omitted it. Disabled via CN_LLM_AGENT_DISCLAIMER=false.
        if self._disclaimer and compliance.needs_disclaimer(answer):
            tail = f"\n\n{compliance.DISCLAIMER}"
            yield TextDelta(text=tail)
            answer = f"{answer}{tail}"

        yield AgentDone(text=answer)

    def _web_search_tool(self) -> dict[str, Any] | None:
        """The Anthropic built-in web-search tool spec, or None when disabled."""
        if self._web_search_max_uses <= 0:
            return None
        return {
            "type": _WEB_SEARCH_TYPE,
            "name": skill.WEB_SEARCH,
            "max_uses": self._web_search_max_uses,
        }

    @staticmethod
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
    """Pull user-facing text from an on_chat_model_stream event.

    A chunk's ``content`` is either a plain string or a list of content blocks
    (Anthropic returns blocks when thinking/tool-use/web-search interleave); we
    take only the text, ignoring thinking, tool-call and search-result deltas.
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
