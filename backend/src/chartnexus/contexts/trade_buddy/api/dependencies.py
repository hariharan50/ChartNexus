"""Per-request assembly for the Trade Buddy routes.

The context imports only the ``build_trade_buddy`` bridge from infrastructure, so
it never acquires a static edge into another context or into the HTTP stack. The
independence contract exempts that single edge — the same arrangement messaging,
report, hugin and five others already use.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from chartnexus.infrastructure.trade_buddy.build_trade_buddy import (
    TradeBuddyServices,
    build_trade_buddy_services,
)
from chartnexus.infrastructure.transport.http.dependencies import CurrentPrincipal

__all__ = ["Services", "TradeBuddyServices", "build_services"]


async def build_services(request: Request, principal: CurrentPrincipal) -> TradeBuddyServices:
    # Trade Buddy is per-user: the services are built *for* the caller, with a
    # state store and channel set bound to their user id. Taking the principal
    # here, rather than leaving each route to pass it, means no route can reach
    # a store that is not scoped to whoever is asking. FastAPI resolves the
    # principal once per request, so routes that also declare it pay nothing.
    return await build_trade_buddy_services(
        request, user_id=principal.user_id, tenant_id=principal.tenant_id
    )


Services = Annotated[TradeBuddyServices, Depends(build_services)]
