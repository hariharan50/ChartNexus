"""Report endpoints — the daily market report (PDF).

* ``GET  /report/availability`` — whether the LLM narrative is on.
* ``GET/PUT /report/enrollment`` — the per-tenant opt-in for the scheduled report.
* ``POST /report/{instrument}/generate`` — build today's report on demand and
  return it as a PDF download.

Every number in the report comes from market data; only the prose is LLM-written.
Not investment advice — educational only.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path
from fastapi.responses import Response

from chartnexus.contexts.report.api.dependencies import Services
from chartnexus.contexts.report.api.schemas import (
    AvailabilityResponse,
    EnrollmentResponse,
    SetEnrollmentRequest,
)
from chartnexus.infrastructure.transport.http.dependencies import CurrentPrincipal

router = APIRouter(prefix="/report", tags=["report"])

InstrumentParam = Annotated[
    str,
    Path(
        description="NIFTY, BANKNIFTY, or SENSEX. This surface is index-only;"
        " the wider F&O catalog is not covered here yet.",
        examples=["NIFTY"],
    ),
]


@router.get(
    "/availability",
    response_model=AvailabilityResponse,
    summary="Whether the report's LLM narrative is available",
)
async def availability(principal: CurrentPrincipal, services: Services) -> AvailabilityResponse:
    _ = principal
    return AvailabilityResponse(available=services.generate.available)


@router.get(
    "/enrollment",
    response_model=EnrollmentResponse,
    summary="Whether the scheduled daily report is on for this tenant",
)
async def get_enrollment(principal: CurrentPrincipal, services: Services) -> EnrollmentResponse:
    return EnrollmentResponse(enabled=await services.get_enrollment(principal.tenant_id))


@router.put(
    "/enrollment",
    response_model=EnrollmentResponse,
    summary="Turn the scheduled daily report on or off",
)
async def set_enrollment(
    principal: CurrentPrincipal,
    services: Services,
    body: SetEnrollmentRequest,
) -> EnrollmentResponse:
    enabled = await services.set_enrollment(principal.tenant_id, enabled=body.enabled)
    return EnrollmentResponse(enabled=enabled)


@router.post(
    "/{instrument_id}/generate",
    summary="Generate today's report on demand and download it as PDF",
    responses={200: {"content": {"application/pdf": {}}, "description": "The report PDF"}},
)
async def generate(
    principal: CurrentPrincipal,
    services: Services,
    instrument_id: InstrumentParam,
) -> Response:
    symbol = instrument_id.strip().upper()
    generated = await services.generate(principal.tenant_id, symbol)
    filename = f"ChartNexus-{symbol}-{generated.report.trading_day.isoformat()}.pdf"
    return Response(
        content=generated.pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
