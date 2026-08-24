"""Per-request assembly for the report routes.

The context imports only the ``build_report`` bridge from infrastructure, so it
never acquires a static edge into other contexts. The independence contract
exempts that single edge. The services type is re-exported so the router
references it through this module.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from marketcompass.infrastructure.report.build_report import (
    ReportServices,
    build_report_services,
)
from marketcompass.infrastructure.transport.http.dependencies import CurrentPrincipal

__all__ = ["ReportServices", "Services", "build_services"]


async def build_services(request: Request, principal: CurrentPrincipal) -> ReportServices:
    return await build_report_services(request, principal.user_id)


Services = Annotated[ReportServices, Depends(build_services)]
