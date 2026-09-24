"""Composition bridge for the global-markets context.

The one module that context imports from infrastructure, the same shape
``build_breadth`` uses. It keeps httpx, Redis and the choice of quote provider
out of the context itself - which is what makes swapping Yahoo for a keyed
provider later a change to this file and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from marketcompass.contexts.global_markets.application.get_global_view import GetGlobalView
from marketcompass.infrastructure.global_markets.gap_journal import RedisGapJournal
from marketcompass.infrastructure.global_markets.nseix.gift_source import (
    NseIxGiftNiftySource,
)
from marketcompass.infrastructure.global_markets.simulated_source import (
    SimulatedGiftNiftySource,
    SimulatedGlobalQuoteSource,
)
from marketcompass.infrastructure.global_markets.yahoo.quote_source import (
    YahooGlobalQuoteSource,
)
from marketcompass.infrastructure.time.clock import SystemClock


@dataclass(frozen=True, slots=True)
class GlobalServices:
    view: GetGlobalView


def build_global_services(container: Any) -> GlobalServices:
    """Assemble the GIA read.

    The live quote source has the simulator behind it for when the provider
    cannot be reached - an outage, a rate limit, a developer offline. The badge
    on the page says which of the two answered, every time.

    GIFT NIFTY reads NSE IX's own market watch, with the simulator behind it
    on the same terms. Its badge is separate from the board's: the two come
    from different providers and either can degrade without the other.
    """
    clock = SystemClock()
    return GlobalServices(
        view=GetGlobalView(
            quotes=YahooGlobalQuoteSource(
                container.http,
                container.redis,
                fallback=SimulatedGlobalQuoteSource(clock),
            ),
            gift=NseIxGiftNiftySource(
                container.http,
                container.redis,
                fallback=SimulatedGiftNiftySource(clock),
            ),
            journal=RedisGapJournal(container.redis),
            clock=clock,
        )
    )
