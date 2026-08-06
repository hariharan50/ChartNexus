"""Synthetic option chains.

Open interest, the ladder and spot all come from :mod:`session_model`, so this
chain is the same book the snapshot archive holds for the same instant — the
Option Chain page, the Open Interest page and the ingest worker cannot disagree.
What is added here is the option-quote dressing the model has no opinion about:
bid/ask around the last price, and a delta curve.

Not a pricing model. Anything computed from it is illustrative, which is why the
chain is stamped ``DataSource.MOCK`` and the UI shows it as simulated.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    DataSource,
    OptionChain,
    OptionQuote,
    Provenance,
    StrikeRow,
)
from marketcompass.infrastructure.brokers.mock.session_model import (
    LADDER_REACH,
    Leg,
    frame_at,
    lot_size,
    strike_step,
)

STRIKES_EITHER_SIDE = LADDER_REACH
_CENTS = Decimal("0.01")
_SPREAD = Decimal("0.5")


def build_option_chain(
    instrument: InstrumentSymbol, moment: datetime, expiry: str | None = None
) -> OptionChain:
    frame = frame_at(instrument.value, moment)
    spot = _money(frame.spot)
    step = strike_step(instrument)

    expiries = upcoming_expiries(moment.date())
    resolved = expiry if expiry in expiries else expiries[0]

    strikes = tuple(
        _build_row(strike=_money(strike), call=call, put=put, spot=spot, step=step)
        for strike, call, put in frame.pairs()
    )

    return OptionChain(
        instrument=instrument,
        expiry=resolved,
        spot_price=spot,
        strikes=strikes,
        provenance=Provenance(source=DataSource.MOCK, fetched_at=moment),
        expiries=expiries,
        lot_size=lot_size(instrument),
        change_percent=Decimal("0.15"),
        future_price=(spot * Decimal("1.0008")).quantize(_CENTS),
        india_vix=Decimal(str(round(13.0 + 2.0 * math.sin(moment.minute / 10), 2))),
        india_vix_change_percent=Decimal("-0.45"),
    )


def upcoming_expiries(today: date, count: int = 6) -> tuple[str, ...]:
    """The next few Thursdays.

    Acceptable only because this is synthetic data. The live provider reads
    expiries from the broker, precisely because real expiry dates move for
    holidays.
    """
    days_ahead = (3 - today.weekday()) % 7 or 7
    first = today + timedelta(days=days_ahead)
    return tuple((first + timedelta(weeks=week)).isoformat() for week in range(count))


def _build_row(*, strike: Decimal, call: Leg, put: Leg, spot: Decimal, step: Decimal) -> StrikeRow:
    moneyness = float((strike - spot) / (step * 10))
    return StrikeRow(
        strike=strike,
        call=_quote(call, delta=_delta(moneyness)),
        put=_quote(put, delta=_delta(moneyness) - 1),
    )


def _quote(leg: Leg, *, delta: float) -> OptionQuote:
    last = _money(leg.ltp)
    return OptionQuote(
        last_price=last,
        open_interest=leg.oi,
        # The day change a broker actually reports. This used to be a made-up
        # fraction of the current OI, which the Open Interest service's
        # single-snapshot tier then inverted to "reconstruct" a session open —
        # producing an open that never existed.
        open_interest_change=leg.oi_change,
        volume=leg.volume,
        implied_volatility=Decimal(str(leg.iv)),
        bid=(last - _SPREAD).quantize(_CENTS),
        ask=(last + _SPREAD).quantize(_CENTS),
        delta=Decimal(str(round(delta, 4))),
    )


def _delta(moneyness: float) -> float:
    """A logistic curve standing in for N(d1): 0.5 at the money, asymptotic."""
    return 1.0 / (1.0 + math.exp(2.5 * moneyness))


def _money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(_CENTS)
