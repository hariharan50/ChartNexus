"""Per-request assembly for the HUGIN read endpoints.

Mirrors the STRYX recipe: the context imports only the ``build_hugin`` bridge from
infrastructure, so it never acquires a static edge into other contexts or the
LangChain/SQLAlchemy stacks. The independence contract exempts that single edge.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.infrastructure.hugin.build_hugin import (
    HuginCallServices,
    HuginChatServices,
    HuginReadServices,
    build_hugin_call_services,
    build_hugin_chat_services,
    build_hugin_read_services,
)
from marketcompass.infrastructure.transport.http.dependencies import (
    CurrentPrincipal,
    get_session,
)


async def build_hugin_services(
    request: Request,
    principal: CurrentPrincipal,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HuginReadServices:
    return await build_hugin_read_services(request, session, principal.user_id)


Services = Annotated[HuginReadServices, Depends(build_hugin_services)]


async def build_hugin_chat(
    request: Request,
    principal: CurrentPrincipal,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HuginChatServices:
    return await build_hugin_chat_services(request, session, principal.user_id, principal.tenant_id)


ChatServices = Annotated[HuginChatServices, Depends(build_hugin_chat)]


async def build_hugin_calls(
    request: Request,
    principal: CurrentPrincipal,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HuginCallServices:
    return await build_hugin_call_services(request, session, principal.user_id)


CallServices = Annotated[HuginCallServices, Depends(build_hugin_calls)]
