"""Wire shapes for the GIA endpoint.

Two conventions the client depends on:

* **Decimals serialise as strings.** FastAPI does that for ``Decimal``, and the
  frontend parses them through its own ``toNumber``. Nothing does float
  arithmetic on a price on the way out.
* **``null`` means unknown, never zero.** A market that did not publish a
  figure arrives as ``null`` and renders as a dash. Coercing it to 0 would turn
  "we do not know" into "it did not move", which is the one lie this page
  exists to avoid telling.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from marketcompass.contexts.global_markets.application.get_global_view import GlobalView
from marketcompass.contexts.global_markets.domain.handoff import (
    Contribution,
    GapPressure,
    ImpliedOpen,
    SessionBand,
)
from marketcompass.contexts.global_markets.domain.markets import (
    GIFT_KEY,
    GIFT_LABEL,
    REGION_LABELS,
    GlobalMarket,
    session_window,
)
from marketcompass.contexts.global_markets.domain.quotes import GlobalQuote


class _Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MarketRowResponse(_Schema):
    """One row of the board."""

    key: str
    label: str
    region: str
    macro: bool
    price: Decimal | None
    change: Decimal | None
    change_percent: Decimal | None
    previous_close: Decimal | None
    spark: list[Decimal]
    #: The market's own session for the current window, in IST, so the board
    #: can print "19:00 - 01:30" without re-deriving a timezone client-side.
    opens_ist: str
    closes_ist: str

    @classmethod
    def of(
        cls, market: GlobalMarket, quote: GlobalQuote | None, session_date: datetime
    ) -> MarketRowResponse:
        if market.round_the_clock:
            opens_ist = closes_ist = "24h"
        else:
            opens_at, closes_at = session_window(market, session_date.date())
            opens_ist = opens_at.strftime("%H:%M")
            closes_ist = closes_at.strftime("%H:%M")

        return cls(
            key=market.key,
            label=market.label,
            region=market.region.value,
            macro=market.macro,
            price=quote.price if quote else None,
            change=quote.change if quote else None,
            change_percent=quote.change_percent if quote else None,
            previous_close=quote.previous_close if quote else None,
            spark=list(quote.spark) if quote else [],
            opens_ist=opens_ist,
            closes_ist=closes_ist,
        )


class BandResponse(_Schema):
    key: str
    label: str
    region: str
    opens_at: datetime
    closes_at: datetime
    state: str
    start_fraction: float
    end_fraction: float
    change_percent: Decimal | None

    @classmethod
    def of(cls, band: SessionBand) -> BandResponse:
        return cls(
            key=band.key,
            label=band.label,
            region=band.region,
            opens_at=band.opens_at,
            closes_at=band.closes_at,
            state=band.state.value,
            start_fraction=round(band.start_fraction, 5),
            end_fraction=round(band.end_fraction, 5),
            change_percent=band.change_percent,
        )


class ContributionResponse(_Schema):
    key: str
    label: str
    region: str
    change_percent: Decimal
    weight: Decimal
    recency: Decimal
    points: Decimal

    @classmethod
    def of(cls, item: Contribution) -> ContributionResponse:
        return cls(
            key=item.key,
            label=item.label,
            region=item.region,
            change_percent=item.change_percent,
            weight=item.weight,
            recency=item.recency,
            points=item.points,
        )


class PressureResponse(_Schema):
    score: Decimal
    band: str
    contributions: list[ContributionResponse]
    #: Weighted markets with no usable quote. Named rather than dropped: a
    #: composite built from four of nine inputs is a different claim from one
    #: built from all nine, and the page says so.
    missing: list[str]

    @classmethod
    def of(cls, pressure: GapPressure) -> PressureResponse:
        return cls(
            score=pressure.score,
            band=pressure.band.value,
            contributions=[ContributionResponse.of(item) for item in pressure.contributions],
            missing=list(pressure.missing),
        )


class ImpliedOpenResponse(_Schema):
    gift_level: Decimal
    nifty_spot: Decimal
    nifty_previous_close: Decimal
    basis: Decimal
    implied_level: Decimal
    gap_points: Decimal
    gap_percent: Decimal
    signal: str

    @classmethod
    def of(cls, implied: ImpliedOpen) -> ImpliedOpenResponse:
        return cls(
            gift_level=implied.gift_level,
            nifty_spot=implied.nifty_spot,
            nifty_previous_close=implied.nifty_previous_close,
            basis=implied.basis,
            implied_level=implied.implied_level,
            gap_points=implied.gap_points,
            gap_percent=implied.gap_percent,
            signal=implied.signal.value,
        )


class WindowResponse(_Schema):
    opened_at: datetime
    closes_at: datetime
    target_session: str
    progress: float


class RegionResponse(_Schema):
    region: str
    label: str
    change_percent: Decimal | None
    members: int


class GlobalViewResponse(_Schema):
    """The whole page, from one instant."""

    as_of: datetime
    window: WindowResponse
    markets: list[MarketRowResponse]
    regions: list[RegionResponse]
    bands: list[BandResponse]
    pressure: PressureResponse
    implied: ImpliedOpenResponse | None
    gift: MarketRowResponse | None
    verdict: str
    source: str
    gift_source: str
    region_labels: dict[str, str]

    @classmethod
    def of(cls, view: GlobalView) -> GlobalViewResponse:
        gift_row = None
        if view.gift is not None:
            gift_row = MarketRowResponse(
                key=GIFT_KEY,
                label=GIFT_LABEL,
                region="india",
                macro=False,
                price=view.gift.price,
                change=view.gift.change,
                change_percent=view.gift.change_percent,
                previous_close=view.gift.previous_close,
                spark=list(view.gift.spark),
                # GIFT runs two sessions spanning most of the day; printing a
                # single window for it would be wrong, so it prints neither.
                opens_ist="--:--",
                closes_ist="--:--",
            )

        return cls(
            as_of=view.as_of,
            window=WindowResponse(
                opened_at=view.window.opened_at,
                closes_at=view.window.closes_at,
                target_session=view.window.target_session.isoformat(),
                progress=round(view.window.progress(view.as_of), 5),
            ),
            markets=[
                MarketRowResponse.of(market, view.quotes.get(market.key), view.as_of)
                for market in view.markets
            ],
            regions=[
                RegionResponse(
                    region=rollup.region,
                    label=rollup.label,
                    change_percent=rollup.change_percent,
                    members=rollup.members,
                )
                for rollup in view.regions
            ],
            bands=[BandResponse.of(band) for band in view.bands],
            pressure=PressureResponse.of(view.pressure),
            implied=ImpliedOpenResponse.of(view.implied) if view.implied else None,
            gift=gift_row,
            verdict=view.verdict.value,
            source=view.source.value,
            gift_source=view.gift_source.value,
            region_labels={region.value: label for region, label in REGION_LABELS.items()},
        )
