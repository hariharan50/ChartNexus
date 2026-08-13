"""Assembles the LangGraph agent from the other contexts' services.

Lives in infrastructure — the only layer allowed to reach across bounded
contexts — so ``copilot`` never imports ``market_data`` or ``options_analytics``
itself. The copilot dependency imports *this* builder, mirroring how the old
guidance bridge was wired.

Every cross-context import is deferred into the function body. The bounded-context
independence contract is checked on *module-level* imports, and the copilot
dependency statically imports this module; keeping the context (and the agent
adapter that pulls them) out of this module's top level keeps that static edge
off copilot. Infrastructure is still free to reach across contexts — this only
prevents copilot inheriting the reach transitively.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.copilot.application.ports import AgentPort
from marketcompass.infrastructure.agent.langgraph.llm import build_chat_model


def build_langgraph_agent(request: Request, session: AsyncSession) -> AgentPort:
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
        # unavailable agent so /copilot/availability answers without pulling in
        # the LangChain stack.
        from marketcompass.infrastructure.agent.langgraph.unavailable import (  # noqa: PLC0415
            UnavailableAgent,
        )

        return UnavailableAgent()

    # Deferred so the copilot dependency that imports this module never acquires
    # a static edge into these contexts (see the module docstring).
    from marketcompass.contexts.market_data.api.dependencies import (  # noqa: PLC0415
        build_market_services,
    )
    from marketcompass.contexts.options_analytics.api.dependencies import (  # noqa: PLC0415
        build_options_analytics_services,
    )
    from marketcompass.infrastructure.agent.langgraph.agent import (  # noqa: PLC0415
        LangGraphAgent,
    )

    market = build_market_services(request, session)
    options = build_options_analytics_services(request, session)
    return LangGraphAgent(
        model=model, market=market, options=options, disclaimer=llm.agent_disclaimer
    )
