"""GIA - Global Index Analysis.

One endpoint, deliberately. The timeline, the pressure gauge and the
implied-open card all describe the same instant; splitting them across three
polled endpoints would let them drift apart on screen for reasons no user could
diagnose.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from marketcompass.contexts.global_markets.api.dependencies import Services
from marketcompass.contexts.global_markets.api.schemas import GlobalViewResponse
from marketcompass.infrastructure.transport.http.dependencies import get_principal

router = APIRouter(prefix="/global", tags=["global"])


@router.get(
    "/view",
    response_model=GlobalViewResponse,
    # Authentication is declared on the route rather than bound to a parameter:
    # nothing on this page varies by tenant, so the principal is required but
    # never read. World index levels are facts about the world.
    dependencies=[Depends(get_principal)],
    summary="World markets, the overnight handoff, and the gap they imply",
    description=(
        "Every tracked index and macro instrument, each one's session placed on "
        "the IST overnight axis, the weighted Global Gap Pressure composite with "
        "its contributions itemised, and GIFT NIFTY's implied open. GIFT is "
        "reported separately from the composite on purpose: it quotes the thing "
        "being predicted, while the rest are inputs to predicting it."
    ),
)
async def global_view(services: Services) -> GlobalViewResponse:
    return GlobalViewResponse.of(await services.view())
