"""Per-request assembly for STRYX.

Wires the LangGraph agent over the tenant's market-data and options-analytics
services, the Redis session store, and the Postgres trade journal. All the
framework-specific pieces (LangGraph, the chat model, the cross-context bridges)
live in infrastructure, so this module never imports another context's internals
beyond their per-request service builders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.stryx.application.ports import SessionStorePort, TradeJournalPort
from marketcompass.contexts.stryx.application.stryx_service import StryxService
from marketcompass.infrastructure.agent.langgraph.build_stryx import build_stryx_agent
from marketcompass.infrastructure.persistence.postgresql.repositories.stryx.call_repository import (
    SqlAlchemyStryxCallRepository,
)
from marketcompass.infrastructure.stryx.redis_session_store import StryxRedisSessionStore
from marketcompass.infrastructure.transport.http.dependencies import (
    CurrentPrincipal,
    get_container,
    get_session,
)


@dataclass(slots=True)
class StryxServices:
    agent: StryxService
    sessions: SessionStorePort
    journal: TradeJournalPort


def build_stryx_services(
    request: Request,
    principal: CurrentPrincipal,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StryxServices:
    container = get_container(request)
    agent = build_stryx_agent(request, session)
    # The journal manages its own sessions: it is written from the streaming
    # response body, after this request's session has finished its unit of work.
    journal = SqlAlchemyStryxCallRepository(container.database)
    sessions = StryxRedisSessionStore(container.redis, principal.tenant_id)
    return StryxServices(
        agent=StryxService(agent=agent, journal=journal),
        sessions=sessions,
        journal=journal,
    )


Services = Annotated[StryxServices, Depends(build_stryx_services)]
