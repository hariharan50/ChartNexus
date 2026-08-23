"""Composition bridge for MME100 — assembles ports from the ``Container``.

The one module the ``mme100`` context is allowed to import from infrastructure.
Mirrors ``build_stryx.py`` / ``build_hugin.py``: it lives here (not in the context)
so the context never acquires a static edge into infrastructure/other contexts, and
the independence contract exempts only the single edge
``mme100.api.dependencies -> infrastructure.mme100.build_mme100``.

Provides the *request* services (chat + sessions + briefing read + enrollment) and
the *worker* pieces (a request-less agent builder, the tenant directory, the
briefing store) that the pre-market loop composes.

Every cross-context / LangChain import is deferred into a function body, for the
same reason as the sibling builders: the independence contract is checked on
module-level imports, and the mme100 dependency statically imports this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.mme100.application.enrollment import (
    GetMme100Enrollment,
    SetMme100Enrollment,
)
from marketcompass.contexts.mme100.application.mme100_service import Mme100Service
from marketcompass.contexts.mme100.application.ports import (
    AgentPort,
    BriefingStorePort,
    SessionStorePort,
    TenantDirectoryPort,
)
from marketcompass.infrastructure.agent.langgraph.user_llm import build_user_chat_model
from marketcompass.infrastructure.mme100.redis_session_store import Mme100RedisSessionStore
from marketcompass.infrastructure.mme100.tenant_directory import SqlAlchemyMme100TenantDirectory
from marketcompass.infrastructure.persistence.postgresql.repositories.mme100.briefing_repository import (
    SqlAlchemyMme100BriefingRepository,
)
from marketcompass.infrastructure.persistence.postgresql.repositories.mme100.enrollment_repository import (
    SqlAlchemyMme100EnrollmentRepository,
)
from marketcompass.infrastructure.transport.http.dependencies import get_container
from marketcompass.shared_kernel.types.identifiers import TenantId, UserId


@dataclass(slots=True)
class Mme100Services:
    """The request side of MME100, wired for one authenticated request."""

    agent: Mme100Service
    sessions: SessionStorePort
    briefing: BriefingStorePort
    get_enrollment: GetMme100Enrollment
    set_enrollment: SetMme100Enrollment


async def build_mme100_services(
    request: Request,
    session: AsyncSession,
    user_id: UserId,
    tenant_id: TenantId,
) -> Mme100Services:
    container = get_container(request)
    agent_port = await _build_agent(container, request, session, user_id)
    enrollment = SqlAlchemyMme100EnrollmentRepository(container.database)
    return Mme100Services(
        agent=Mme100Service(agent=agent_port),
        sessions=Mme100RedisSessionStore(container.redis, tenant_id),
        briefing=SqlAlchemyMme100BriefingRepository(container.database),
        get_enrollment=GetMme100Enrollment(enrollment),
        set_enrollment=SetMme100Enrollment(enrollment),
    )


async def _build_agent(
    container: Any, request: Request, session: AsyncSession, user_id: UserId
) -> AgentPort:
    """The MME100 agent for a request, over the caller's market/options services."""
    model = await build_user_chat_model(container, session, user_id)
    if model is None:
        from marketcompass.infrastructure.agent.langgraph.mme100_unavailable import (  # noqa: PLC0415
            UnavailableMme100Agent,
        )

        return UnavailableMme100Agent()

    from marketcompass.contexts.market_data.api.dependencies import (  # noqa: PLC0415
        build_market_services,
    )
    from marketcompass.contexts.options_analytics.api.dependencies import (  # noqa: PLC0415
        build_options_analytics_services,
    )
    from marketcompass.infrastructure.agent.langgraph.mme100_agent import (  # noqa: PLC0415
        Mme100LangGraphAgent,
    )

    market = build_market_services(request, session)
    options = build_options_analytics_services(request, session)
    return Mme100LangGraphAgent(
        model=model,
        market=market,
        options=options,
        disclaimer=container.settings.llm.agent_disclaimer,
        web_search_max_uses=container.settings.mme100.web_search_max_uses,
    )


async def build_mme100_worker_agent(
    container: Any, session: AsyncSession, user_id: UserId
) -> AgentPort:
    """The MME100 agent for the pre-market worker — request-less.

    Uses the ``*_from(container, session)`` service builders so a worker with a
    ``Container`` but no request can still read the market. The session must stay
    open for the whole briefing run, because the agent calls tools ad hoc; the
    caller owns that session (a committing one, so write-through caches persist).
    """
    model = await build_user_chat_model(container, session, user_id)
    if model is None:
        from marketcompass.infrastructure.agent.langgraph.mme100_unavailable import (  # noqa: PLC0415
            UnavailableMme100Agent,
        )

        return UnavailableMme100Agent()

    from marketcompass.contexts.market_data.api.dependencies import (  # noqa: PLC0415
        build_market_services_from,
    )
    from marketcompass.contexts.options_analytics.api.dependencies import (  # noqa: PLC0415
        build_options_analytics_services_from,
    )
    from marketcompass.infrastructure.agent.langgraph.mme100_agent import (  # noqa: PLC0415
        Mme100LangGraphAgent,
    )

    market = build_market_services_from(container, session)
    options = build_options_analytics_services_from(container, session)
    return Mme100LangGraphAgent(
        model=model,
        market=market,
        options=options,
        disclaimer=container.settings.llm.agent_disclaimer,
        web_search_max_uses=container.settings.mme100.web_search_max_uses,
    )


def build_mme100_directory(container: Any) -> TenantDirectoryPort:
    return SqlAlchemyMme100TenantDirectory(container.database)


def build_mme100_briefing_store(container: Any) -> BriefingStorePort:
    return SqlAlchemyMme100BriefingRepository(container.database)
