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
from marketcompass.infrastructure.agent.langgraph.user_llm import build_user_chat_model
from marketcompass.shared_kernel.types.identifiers import UserId


async def build_langgraph_agent(
    request: Request, session: AsyncSession, user_id: UserId
) -> AgentPort:
    container = request.app.state.container
    model = await build_user_chat_model(container, session, user_id)
    if model is None:
        # The user has no saved key (or the 'agent' extra isn't installed).
        # Return the import-safe unavailable agent so /copilot/availability
        # answers without pulling in the LangChain stack.
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
        model=model,
        market=market,
        options=options,
        disclaimer=container.settings.llm.agent_disclaimer,
    )
