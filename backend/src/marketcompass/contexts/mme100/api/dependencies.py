"""Per-request assembly for MME100.

Mirrors the STRYX/HUGIN recipe: the context imports only the ``build_mme100``
bridge from infrastructure, so it never acquires a static edge into other contexts
or the LangChain/SQLAlchemy stacks. The independence contract exempts that single
edge.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.infrastructure.mme100.build_mme100 import (
    Mme100Services,
    build_mme100_services,
)
from marketcompass.infrastructure.transport.http.dependencies import (
    CurrentPrincipal,
    get_session,
)

# Re-exported so the router (and any other context module) references the services
# type through this dependency module — the single sanctioned edge to the
# infrastructure bridge — rather than importing the bridge directly.
__all__ = ["Mme100Services", "Services", "build_services"]


async def build_services(
    request: Request,
    principal: CurrentPrincipal,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Mme100Services:
    return await build_mme100_services(request, session, principal.user_id, principal.tenant_id)


Services = Annotated[Mme100Services, Depends(build_services)]
