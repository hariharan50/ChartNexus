"""LangGraph implementation of STRYX's ``AgentPort``.

A single ReAct agent (``create_react_agent``) over the same read-only market
tools HELLA reads, driven with Claude — but with STRYX's persona, its full
five-style playbook, the discipline frame, and the [STRYX CALL] output contract.
It streams LangGraph events and translates them into STRYX's ``AgentEvent``
vocabulary the SSE transport speaks.

Deliberately separate from HELLA's ``LangGraphAgent`` rather than a shared
generic: the two contexts stay isolated (neither imports the other's domain), and
HELLA's working adapter is left untouched. The only reused pieces are the
low-level, domain-agnostic infra helpers — the tool builder and the chat-model
builder.

Unlike HELLA there is no planner: STRYX scans the whole read-only surface every
turn (its edge is reacting to rate-of-change across OI / PCR / price / momentum
together), so the executor always gets the full ``CORE_TOOLS`` set.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from marketcompass.contexts.market_data.api.dependencies import MarketServices
from marketcompass.contexts.options_analytics.api.dependencies import OptionsAnalyticsServices
from marketcompass.contexts.stryx.application.ports import (
    AgentDone,
    AgentEvent,
    StylesConsidered,
    TextDelta,
    ToolFinished,
    ToolStarted,
    Turn,
)
from marketcompass.contexts.stryx.domain import compliance, entry_styles, persona
from marketcompass.infrastructure.agent.langgraph.stryx_planner import classify_intent
from marketcompass.infrastructure.agent.langgraph.tools import build_agent_tools
from marketcompass.shared_kernel.types.identifiers import TenantId

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

# Friendly titles for the tool chips the UI renders — STRYX reads the same tools
# as HELLA. Falls back to a generic label so a new tool never breaks the surface.
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

# STRYX pulls the full read-only surface in one scan (~9 tools, one at a time,
# ~19 super-steps), so the ceiling must clear that with headroom.
_RECURSION_LIMIT = 40


class StryxLangGraphAgent:
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
        *,
        cap_reached: bool,
    ) -> AsyncIterator[AgentEvent]:
        model = self._model
        if model is None:  # transport should have gated on `available`
            raise RuntimeError("agent is not available: no model configured")

        # Route first: is this a setup request, or just talk? A greeting or a
        # general question gets a friendly reply with no tools and no template;
        # only a real scan runs the playbook.
        intent = await classify_intent(model, question, history)
        if intent == "conversation":
            async for event in self._converse(model, question, history):
                yield event
            return

        async for event in self._scan(
            model, tenant_id, symbol, question, history, cap_reached=cap_reached
        ):
            yield event

    async def _converse(
        self, model: BaseChatModel, question: str, history: list[Turn]
    ) -> AsyncIterator[AgentEvent]:
        """Small talk: STRYX as a friendly teammate — no tools, no call template."""
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

    async def _scan(
        self,
        model: BaseChatModel,
        tenant_id: TenantId,
        symbol: str,
        question: str,
        history: list[Turn],
        *,
        cap_reached: bool,
    ) -> AsyncIterator[AgentEvent]:
        """A setup hunt: the full tool-calling scan that emits a [STRYX CALL]."""
        from langgraph.errors import GraphRecursionError  # noqa: PLC0415
        from langgraph.prebuilt import create_react_agent  # noqa: PLC0415

        # STRYX weighs the whole playbook every scan — surface the five styles as
        # chips so the UI shows the framework it is reasoning through.
        yield StylesConsidered(titles=entry_styles.titles())

        allowed = set(entry_styles.CORE_TOOLS)
        tools = [
            t
            for t in build_agent_tools(tenant_id, self._market, self._options)
            if t.name in allowed
        ]
        system = persona.compose_system(cap_reached=cap_reached)
        graph = create_react_agent(model, tools, prompt=system)

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
            # Ran out of tool round-trips. Return a graceful NO-TRADE-shaped nudge
            # rather than a dead-end error, keeping any partial text streamed.
            if not answer_parts:
                nudge = (
                    "[STRYX CALL]\nStatus: NO TRADE\nReasoning: Couldn't get a clean read in "
                    "time — too much to weigh in one pass. Ask me about one instrument and "
                    "I'll scan it fast."
                )
                yield TextDelta(text=nudge)
                answer_parts.append(nudge)

        answer = "".join(answer_parts).strip()
        # Compliance guardrail: every call carries the "paper-trade only" framing
        # even if the model omitted it. Disabled via MC_LLM_AGENT_DISCLAIMER=false.
        if self._disclaimer and compliance.needs_disclaimer(answer):
            tail = f"\n\n{compliance.DISCLAIMER}"
            yield TextDelta(text=tail)
            answer = f"{answer}{tail}"

        yield AgentDone(text=answer)

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
    (Anthropic returns blocks when thinking/tool-use interleave); we take only the
    text, ignoring thinking and tool-call deltas.
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
