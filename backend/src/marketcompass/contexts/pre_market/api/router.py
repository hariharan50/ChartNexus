"""PMS - the pre-market screener.

One endpoint, deliberately, for the same reason GIA has one: the regime score,
the level ladder and the gap card all describe the same instant, and eleven
polled endpoints would let them disagree on screen for reasons no user could
diagnose.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from marketcompass.contexts.pre_market.api.dependencies import Services
from marketcompass.contexts.pre_market.api.schemas import PreMarketViewResponse
from marketcompass.contexts.pre_market.application.get_pre_market_view import (
    PreMarketQuery,
)
from marketcompass.contexts.pre_market.domain.readings import HEADLINE_INDICES
from marketcompass.infrastructure.transport.http.dependencies import get_principal

router = APIRouter(prefix="/pre-market", tags=["pre-market"])

_FOCUS_CHOICES = ", ".join(index.symbol for index in HEADLINE_INDICES)


@router.get(
    "/view",
    response_model=PreMarketViewResponse,
    # Required but never read: index levels, the overnight board and the option
    # chain are facts about the market, not about whoever asked.
    dependencies=[Depends(get_principal)],
    summary="The whole pre-market read, from one instant",
    description=(
        "Headline cards for NIFTY, BANK NIFTY and SENSEX with their gaps, plus "
        "the level ladder, technicals, volatility, expected move, option "
        "positioning, overnight global cues, breadth, flows and the regime "
        "scorecard for the focused index.\n\n"
        "Every panel carries its own status. One dead upstream degrades one "
        "section with a stated reason rather than blanking the page, so a "
        "`null` panel always arrives with a `status` explaining itself."
    ),
)
async def pre_market_view(
    services: Services,
    focus: Annotated[
        str,
        Query(description=f"Which index the deep panels describe: {_FOCUS_CHOICES}."),
    ] = "NIFTY",
) -> PreMarketViewResponse:
    return PreMarketViewResponse.of(await services.view(PreMarketQuery(focus=focus)))
