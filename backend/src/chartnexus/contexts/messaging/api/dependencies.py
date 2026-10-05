"""Per-request assembly for the messaging routes.

The context imports only the ``build_messaging`` bridge from infrastructure, so it
never acquires a static edge into other contexts or the HTTP/SQLAlchemy stacks.
The independence contract exempts that single edge. The services type is
re-exported here so the router references it through this module.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from chartnexus.infrastructure.messaging.build_messaging import (
    MessagingServices,
    build_messaging_services,
)

__all__ = ["MessagingServices", "Services", "build_services"]


def build_services(request: Request) -> MessagingServices:
    return build_messaging_services(request)


Services = Annotated[MessagingServices, Depends(build_services)]
