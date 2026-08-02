"""Synthetic quotes.

Deterministic by design: the same instrument at the same minute always produces
the same price, so tests are stable and a developer's screen does not flicker
with meaningless noise. It is not a market simulation and makes no attempt to
be realistic beyond plausible magnitudes.
"""

from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    DataSource,
    Provenance,
    Quote,
)

# Rough index levels, only so the numbers look like the right instrument.
_BASE_LEVEL: dict[InstrumentSymbol, Decimal] = {
    InstrumentSymbol.NIFTY: Decimal(24000),
    InstrumentSymbol.BANKNIFTY: Decimal(51000),
    InstrumentSymbol.SENSEX: Decimal(79000),
}

_STRIKE_STEP: dict[InstrumentSymbol, Decimal] = {
    InstrumentSymbol.NIFTY: Decimal(50),
    InstrumentSymbol.BANKNIFTY: Decimal(100),
    InstrumentSymbol.SENSEX: Decimal(100),
}

_LOT_SIZE: dict[InstrumentSymbol, int] = {
    InstrumentSymbol.NIFTY: 75,
    InstrumentSymbol.BANKNIFTY: 30,
    InstrumentSymbol.SENSEX: 20,
}

_SWING_PERCENT = Decimal("0.006")


def base_level(instrument: InstrumentSymbol) -> Decimal:
    return _BASE_LEVEL[instrument]


def strike_step(instrument: InstrumentSymbol) -> Decimal:
    return _STRIKE_STEP[instrument]


def lot_size(instrument: InstrumentSymbol) -> int:
    return _LOT_SIZE[instrument]


def spot_price(instrument: InstrumentSymbol, moment: datetime) -> Decimal:
    """A slow sine wave around the base level, keyed to the minute."""
    base = base_level(instrument)
    phase = (moment.hour * 60 + moment.minute) / 240.0
    swing = Decimal(str(round(math.sin(phase + len(instrument.value)), 6)))
    return (base * (Decimal(1) + swing * _SWING_PERCENT)).quantize(Decimal("0.01"))


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
