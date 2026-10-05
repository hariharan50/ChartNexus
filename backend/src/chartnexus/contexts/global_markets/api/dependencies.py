"""Per-request assembly for the global-markets routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from chartnexus.infrastructure.global_markets.build_global import (
    GlobalServices,
    build_global_services,
)
from chartnexus.infrastructure.transport.http.dependencies import get_container


def build_services(request: Request) -> GlobalServices:
    return build_global_services(get_container(request))


Services = Annotated[GlobalServices, Depends(build_services)]
