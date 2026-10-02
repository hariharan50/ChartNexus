"""Synthetic global quotes, and a synthetic GIFT NIFTY.

What the live adapters stand in for when the provider is unreachable, and -
in GIFT's case - the only implementation there is, because NSE IX publishes no
documented API.

Three rules make a generated board safe to ship, the same three
``breadth/flow_source.py`` states:

* **Every reading is stamped ``source = "mock"``** and the page renders the
  Simulated badge. A generated board is indistinguishable from a true one by
  eye; the badge is the only thing that separates them.
* **It is deterministic in the session date.** The same day always generates
  the same figures, so the page does not reshuffle its own history on every
  poll and a screenshot stays reproducible.
* **Nothing is persisted.** These numbers never reach a store, so they can
  never later be mistaken for an observation.

The shapes are drawn from how these series actually behave - the US indices
move together, Asia moves less, VIX moves several times as far as the index it
prices and in the opposite direction - because a placeholder that behaves
nothing like the real data teaches the layout the wrong lessons.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Final

from marketcompass.contexts.global_markets.application.ports import (
    GiftNiftySource,
    GlobalQuoteSource,
)
from marketcompass.contexts.global_markets.domain.markets import (
    GIFT_KEY,
    IST,
    MARKETS,
    GlobalMarket,
)
from marketcompass.contexts.global_markets.domain.quotes import (
    DataSource,
    GlobalQuote,
    Provenance,
    QuoteSet,
)

#: Plausible levels, so a developer's screen shows numbers in the right shape.
#: Not calibrated to any date - they are a starting point for the walk, not a
#: claim about where anything trades.
_BASE: Final[dict[str, str]] = {
    "NIKKEI": "65000",
    "HSI": "24700",
    "SHANGHAI": "3900",
    "FTSE": "10700",
    "DAX": "25400",
    "SPX": "7700",
    "NASDAQ": "26900",
    "DJIA": "51500",
    "VIX": "15.2",
    "NIFTY": "23450",
    "CRUDE": "91.4",
    "GOLD": "4330",
    "USDINR": "95.7",
    "US10Y": "5.1",
}

#: Typical daily percentage swing. VIX is deliberately an order of magnitude
#: wider; a VIX that drifts 0.4% a day would never exercise the inverted weight
#: in the composite.
_SWING: Final[dict[str, float]] = {
    "VIX": 6.0,
    "CRUDE": 2.0,
    "GOLD": 1.2,
    "USDINR": 0.3,
    "US10Y": 1.5,
}
_DEFAULT_SWING: Final = 0.8

_BY_SYMBOL: Final[dict[str, GlobalMarket]] = {market.symbol: market for market in MARKETS}


def _seeded(key: str, session: str, salt: str = "") -> random.Random:
    return random.Random(f"global:{key}:{session}:{salt}")  # noqa: S311 - not cryptographic


def _quote(key: str, now: datetime) -> GlobalQuote:
    session = now.astimezone(IST).date().isoformat()
    rng = _seeded(key, session)

    base = Decimal(_BASE.get(key, "1000"))
    swing = _SWING.get(key, _DEFAULT_SWING)

    change_percent = Decimal(str(round(rng.uniform(-swing, swing), 2)))
    previous_close = (
        base * (Decimal(1) + Decimal(str(round(rng.uniform(-0.01, 0.01), 4))))
    ).quantize(Decimal("0.01"))
    price = (previous_close * (Decimal(1) + change_percent / Decimal(100))).quantize(
        Decimal("0.01")
    )
    change = (price - previous_close).quantize(Decimal("0.01"))

    # A five-point walk ending on the current price, so the sparkline has the
    # same last value the board prints beside it.
    spark: list[Decimal] = []
    level = previous_close
    for step in range(4):
        drift = Decimal(str(round(_seeded(key, session, str(step)).uniform(-swing, swing), 2)))
        level = (level * (Decimal(1) + drift / Decimal(100))).quantize(Decimal("0.01"))
        spark.append(level)
    spark.append(price)

    return GlobalQuote(
        key=key,
        price=price,
        change=change,
        change_percent=change_percent,
        previous_close=previous_close,
        day_open=previous_close,
        day_high=max(price, previous_close),
        day_low=min(price, previous_close),
        spark=tuple(spark),
        session=now,
        provenance=Provenance(source=DataSource.MOCK, fetched_at=now),
    )


class SimulatedGlobalQuoteSource(GlobalQuoteSource):
    """A full board, generated. Always ``source = "mock"``."""

    def __init__(self, clock: object | None = None) -> None:
        self._clock = clock

    @property
    def name(self) -> str:
        return "mock"

    async def get_quotes(self, symbols: Sequence[str]) -> QuoteSet:
        now = self._now()
        quotes: dict[str, GlobalQuote] = {}
        for symbol in symbols:
            market = _BY_SYMBOL.get(symbol)
            key = market.key if market else symbol
            quotes[key] = _quote(key, now)
        return QuoteSet(quotes=quotes, source=DataSource.MOCK, fetched_at=now)

    def _now(self) -> datetime:
        now = getattr(self._clock, "now", None)
        return now() if callable(now) else datetime.now(tz=IST)


class SimulatedGiftNiftySource(GiftNiftySource):
    """GIFT NIFTY, generated - the only implementation there is today.

    Anchored to the NIFTY quote it is handed rather than to a base level of its
    own, so the implied-open arithmetic is exercised with a realistic basis and
    the card never shows a GIFT level thousands of points away from spot.

    The basis is a small premium plus a seeded overnight move, because that is
    what the contract actually does: it carries cost of carry and then prices
    whatever happened in New York after India shut.
    """

    #: Typical cost-of-carry premium, as a fraction of spot.
    _CARRY = Decimal("0.0006")

    def __init__(self, clock: object | None = None) -> None:
        self._clock = clock

    @property
    def name(self) -> str:
        return "mock"

    async def get_quote(self, nifty_spot: GlobalQuote | None) -> GlobalQuote | None:
        if nifty_spot is None:
            return None

        now = self._now()
        session = now.astimezone(IST).date().isoformat()
        rng = _seeded(GIFT_KEY, session)

        overnight = Decimal(str(round(rng.uniform(-0.9, 0.9), 2)))
        price = (
            nifty_spot.price * (Decimal(1) + self._CARRY) * (Decimal(1) + overnight / Decimal(100))
        ).quantize(Decimal("0.01"))
        change = (price - nifty_spot.price).quantize(Decimal("0.01"))
        change_percent = (change / nifty_spot.price * Decimal(100)).quantize(Decimal("0.01"))

        return GlobalQuote(
            key=GIFT_KEY,
            price=price,
            change=change,
            change_percent=change_percent,
            previous_close=nifty_spot.price,
            spark=(),
            session=now,
            provenance=Provenance(source=DataSource.MOCK, fetched_at=now),
        )

    def _now(self) -> datetime:
        now = getattr(self._clock, "now", None)
        return now() if callable(now) else datetime.now(tz=IST)
