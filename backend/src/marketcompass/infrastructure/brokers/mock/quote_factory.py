"""Synthetic quotes.

Deterministic by design: the same instrument at the same minute always produces
the same price, so tests are stable and a developer's screen does not flicker
with meaningless noise.

The price itself comes from :mod:`session_model`, which is the single simulation
behind every mock number in the app. This module used to run its own sine wave;
the option-chain factory and the snapshot seeder ran two more, and the three
disagreed. Everything price-shaped now reads the one walk.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    DataSource,
    FuturesQuote,
    Provenance,
    Quote,
)
from marketcompass.infrastructure.brokers.mock.session_model import (
    base_level,
    lot_size,
    spot_at,
    strike_step,
)

__all__ = [
    "base_level",
    "build_futures_quote",
    "build_quote",
    "lot_size",
    "spot_price",
    "strike_step",
]

_SWING_PERCENT = Decimal("0.006")


def spot_price(instrument: InstrumentSymbol, moment: datetime) -> Decimal:
    """The simulated index level at ``moment``.

    Thin by design — it is the seam every existing caller already imports, so
    pointing it at the shared walk is what makes the dashboard, the futures
    strip, the option chain and the Open Interest page agree on one number.
    """
    return spot_at(instrument.value, moment)


def build_quote(instrument: InstrumentSymbol, moment: datetime) -> Quote:
    price = spot_price(instrument, moment)
    base = base_level(instrument)
    change = (price - base).quantize(Decimal("0.01"))
    change_percent = ((change / base) * Decimal(100)).quantize(Decimal("0.01"))

    return Quote(
        instrument=instrument,
        price=price,
        change=change,
        change_percent=change_percent,
        provenance=Provenance(source=DataSource.MOCK, fetched_at=moment),
    )


# Futures trade at a small cost-of-carry premium to spot; a flat 7 bps keeps the
# synthetic number visibly a future without pretending to model the basis.
_FUTURES_BASIS = Decimal("0.0007")


def build_futures_quote(
    instrument: InstrumentSymbol, moment: datetime, *, contract: str, expiry: date
) -> FuturesQuote:
    spot = spot_price(instrument, moment)
    price = (spot * (Decimal(1) + _FUTURES_BASIS)).quantize(Decimal("0.01"))
    base = base_level(instrument)
    change = (price - base).quantize(Decimal("0.01"))
    change_percent = ((change / base) * Decimal(100)).quantize(Decimal("0.01"))

    # Deterministic day range and volume, keyed to the minute like the spot.
    swing = (price * _SWING_PERCENT).quantize(Decimal("0.01"))
    volume = 100_000 + (moment.hour * 60 + moment.minute) * 137

    return FuturesQuote(
        instrument=instrument,
        contract=contract,
        expiry=expiry.isoformat(),
        price=price,
        change=change,
        change_percent=change_percent,
        volume=volume,
        day_high=(price + swing).quantize(Decimal("0.01")),
        day_low=(price - swing).quantize(Decimal("0.01")),
        provenance=Provenance(source=DataSource.MOCK, fetched_at=moment),
    )
