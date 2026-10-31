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

__all__ = ["Services", "TradeBuddyServices", "build_services"]


async def build_services(request: Request) -> TradeBuddyServices:
    # Async because assembling the services reads the connected alert bot
    # from the database; FastAPI awaits an async dependency as-is.
    return await build_trade_buddy_services(request)


Services = Annotated[TradeBuddyServices, Depends(build_services)]
