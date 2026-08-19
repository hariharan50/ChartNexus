"""Assembles STRYX's LangGraph agent from the other contexts' services.

Mirrors ``build.py`` (HELLA's builder). Lives in infrastructure — the only layer
allowed to reach across bounded contexts — so ``stryx`` never imports
``market_data`` or ``options_analytics`` itself. The stryx dependency imports
*this* builder.

Every cross-context import is deferred into the function body, for the same
reason as HELLA's builder: the bounded-context independence contract is checked on
module-level imports, and the stryx dependency statically imports this module, so
keeping the contexts (and the LangChain adapter) out of this module's top level
keeps that static edge off ``stryx``.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.stryx.application.ports import AgentPort
from marketcompass.infrastructure.agent.langgraph.llm import build_chat_model


def build_stryx_agent(request: Request, session: AsyncSession) -> AgentPort:
    container = request.app.state.container
    llm = container.settings.llm
    model = build_chat_model(
        provider=llm.provider,
        api_key=llm.anthropic_api_key.get_secret_value(),
        model=llm.resolved_model,
        max_output_tokens=llm.max_output_tokens,
        request_timeout_seconds=llm.request_timeout_seconds,
    )
    if model is None:
        # No key, or the 'agent' extra isn't installed. Return the import-safe
        # unavailable agent so /stryx/availability answers without pulling in the
        # LangChain stack.
        from marketcompass.infrastructure.agent.langgraph.stryx_unavailable import (  # noqa: PLC0415
            UnavailableStryxAgent,
        )

        return UnavailableStryxAgent()

    # Deferred so the stryx dependency that imports this module never acquires a
    # static edge into these contexts (see the module docstring).
    from marketcompass.contexts.market_data.api.dependencies import (  # noqa: PLC0415
        build_market_services,
    )
    from marketcompass.contexts.options_analytics.api.dependencies import (  # noqa: PLC0415
        build_options_analytics_services,
    )
    from marketcompass.infrastructure.agent.langgraph.stryx_agent import (  # noqa: PLC0415
        StryxLangGraphAgent,
    )

    market = build_market_services(request, session)
    options = build_options_analytics_services(request, session)
    return StryxLangGraphAgent(
        model=model, market=market, options=options, disclaimer=llm.agent_disclaimer
    )
