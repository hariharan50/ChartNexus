"""The whole GIA page, assembled in one read.

**One query, not five.** The timeline, the pressure gauge and the implied-open
card all describe the same instant, and three independently polled endpoints
would let them drift apart on screen - a gauge computed from an 09:04 quote set
sitting beside a timeline drawn from an 09:06 one, disagreeing for reasons no
user could ever diagnose. They are read together and rendered together.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from marketcompass.contexts.global_markets.application.ports import (
    Clock,
    GapJournal,
    GiftNiftySource,
    GlobalQuoteSource,
)
from marketcompass.contexts.global_markets.domain.handoff import (
    Agreement,
    GapPressure,
    ImpliedOpen,
    OvernightWindow,
    RegionRollup,
    SessionBand,
    agreement,
    gap_pressure,
    implied_open,
    overnight_window,
    prediction_from,
    region_rollup,
    session_bands,
)
from marketcompass.contexts.global_markets.domain.markets import (
    MARKETS,
    REGION_LABELS,
    GlobalMarket,
)
from marketcompass.contexts.global_markets.domain.quotes import (
    DataSource,
    GlobalQuote,
    QuoteSet,
)


@dataclass(frozen=True, slots=True)
class GlobalView:
    """Everything the page renders, from one instant."""

    as_of: datetime
    window: OvernightWindow
    quotes: QuoteSet
    gift: GlobalQuote | None
    bands: tuple[SessionBand, ...]
    pressure: GapPressure
    implied: ImpliedOpen | None
    verdict: Agreement
    regions: tuple[RegionRollup, ...]
    #: Ordered as the board renders them, so the API layer does no sorting.
    markets: tuple[GlobalMarket, ...]
    source: DataSource
    gift_source: DataSource


class GetGlobalView:
    """Read the world, weigh it, and say what it implies for the open."""

    def __init__(
        self,
        *,
        quotes: GlobalQuoteSource,
        gift: GiftNiftySource,
        journal: GapJournal,
        clock: Clock,
    ) -> None:
        self._quotes = quotes
        self._gift = gift
        self._journal = journal
        self._clock = clock

    async def __call__(self) -> GlobalView:
        """No query object: nothing on this page varies by tenant.

        World index levels are facts about the world, not about whoever asked,
        so they are read once and cached globally - the same reasoning the NSE
        flow source applies to exchange publications. The endpoint still
        requires an authenticated principal; it just does not branch on one.
        """
        now = self._clock.now()
        window = overnight_window(now)

        quote_set = await self._quotes.get_quotes([market.symbol for market in MARKETS])
        nifty = quote_set.get("NIFTY")
        gift = await self._gift.get_quote(nifty)

        bands = session_bands(window, quote_set, now)
        pressure = gap_pressure(window, quote_set, now)
        implied = implied_open(gift, nifty, now)

        # Journalled on every read, keyed by target session so repeated polls
        # through the night overwrite rather than accumulate. The port promises
        # not to raise: nothing on screen depends on the write landing, and a
        # Redis hiccup must not take the page down.
        await self._journal.record(prediction_from(window, pressure, implied, now))

        gift_source = (
            gift.provenance.source
            if gift is not None and gift.provenance is not None
            else DataSource.MOCK
        )

        return GlobalView(
            as_of=now,
            window=window,
            quotes=quote_set,
            gift=gift,
            bands=bands,
            pressure=pressure,
            implied=implied,
            verdict=agreement(pressure, implied),
            regions=region_rollup(MARKETS, quote_set, REGION_LABELS_BY_VALUE),
            markets=MARKETS,
            source=quote_set.source,
            gift_source=gift_source,
        )


#: ``region_rollup`` is keyed by the enum's *value* because that is what the
#: rollup rows carry; building the lookup once here keeps the query tidy.
REGION_LABELS_BY_VALUE = {region.value: label for region, label in REGION_LABELS.items()}
