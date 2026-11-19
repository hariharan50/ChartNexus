"""Per-request assembly for the API monitor routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from chartnexus.infrastructure.api_monitor.build_api_monitor import (
    ApiMonitorServices,
    build_api_monitor,
)
from chartnexus.infrastructure.transport.http.dependencies import get_container


def build_services(request: Request) -> ApiMonitorServices:
    return build_api_monitor(get_container(request))


Services = Annotated[ApiMonitorServices, Depends(build_services)]
