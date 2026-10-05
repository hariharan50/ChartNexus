"""Per-request assembly for the AI Console (Hella).

Wires the LangGraph agent over the tenant's market-data and options-analytics
services, plus the Redis session store. All the framework-specific pieces
(LangGraph, the chat model, the cross-context service bridges) live in
infrastructure, so this module never imports another context's internals beyond
their per-request service builders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from chartnexus.contexts.copilot.application.agent_service import AgentService
from chartnexus.contexts.copilot.application.ports import SessionStorePort
from chartnexus.infrastructure.agent.langgraph.build import build_langgraph_agent
from chartnexus.infrastructure.copilot.redis_session_store import RedisSessionStore
from chartnexus.infrastructure.transport.http.dependencies import (
    CurrentPrincipal,
    get_container,
    get_session,
)


@dataclass(slots=True)
class CopilotServices:
    agent: AgentService
    sessions: SessionStorePort


async def build_copilot_services(
    request: Request,
    principal: CurrentPrincipal,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CopilotServices:
    container = get_container(request)
    agent = await build_langgraph_agent(request, session, principal.user_id)
    sessions = RedisSessionStore(container.redis, principal.tenant_id)
    return CopilotServices(agent=AgentService(agent=agent), sessions=sessions)


Services = Annotated[CopilotServices, Depends(build_copilot_services)]
