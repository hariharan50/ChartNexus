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
from marketcompass.infrastructure.agent.langgraph.user_llm import build_user_chat_model
from marketcompass.shared_kernel.types.identifiers import UserId


async def build_stryx_agent(request: Request, session: AsyncSession, user_id: UserId) -> AgentPort:
    container = request.app.state.container
    model = await build_user_chat_model(container, session, user_id)
    if model is None:
        # The user has no saved key (or the 'agent' extra isn't installed).
        # Return the import-safe unavailable agent so /stryx/availability answers
        # without pulling in the LangChain stack.
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
        model=model,
        market=market,
        options=options,
        disclaimer=container.settings.llm.agent_disclaimer,
    )
