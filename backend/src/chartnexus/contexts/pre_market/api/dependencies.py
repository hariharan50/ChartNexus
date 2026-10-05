"""Per-request assembly for the pre-market routes.

The one module in this context that reaches into infrastructure, and it reaches
for exactly one thing: the bridge. ``tests/architecture`` forbids importing
another context from here, with no exemption list, so the bridge is how PMS
talks to market data, options, the global board and breadth.
``pyproject.toml`` carries one ``ignore_imports`` line for this edge, because
import-linter follows the bridge's transitive reach and would otherwise read it
as PMS depending on four contexts.

The principal is read rather than merely required: nothing on this page varies
by tenant, but the upstream services want a tenant on their queries, and this
is where it gets bound.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from chartnexus.infrastructure.pre_market.build_pre_market import (
    PreMarketServices,
    build_pre_market_services,
)
from chartnexus.infrastructure.transport.http.dependencies import (
    CurrentPrincipal,
    get_container,
    get_session,
)


def build_services(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: CurrentPrincipal,
) -> PreMarketServices:
    return build_pre_market_services(get_container(request), session, principal.tenant_id)


Services = Annotated[PreMarketServices, Depends(build_services)]
