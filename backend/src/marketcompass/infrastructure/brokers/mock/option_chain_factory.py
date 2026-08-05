"""Synthetic option chains.

Enough structure to exercise the analytics: intrinsic value plus a time-value
curve, open interest peaking near round strikes, and a put/call skew. Every
number is deterministic given the instrument and minute.

Not a pricing model. Anything computed from this is illustrative, which is why
the chain is stamped ``DataSource.MOCK`` and the UI shows it as simulated.
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
from marketcompass.infrastructure.brokers.mock.quote_factory import (
    lot_size,
    spot_price,
    strike_step,
)

STRIKES_EITHER_SIDE = 20
_CENTS = Decimal("0.01")


def build_option_chain(
    instrument: InstrumentSymbol, moment: datetime, expiry: str | None = None
) -> OptionChain:
    spot = spot_price(instrument, moment)
    step = strike_step(instrument)
    atm = (spot / step).to_integral_value() * step

    expiries = upcoming_expiries(moment.date())
    resolved = expiry if expiry in expiries else expiries[0]
    days_left = max(1, (date.fromisoformat(resolved) - moment.date()).days)

    strikes = tuple(
        _build_row(strike=atm + step * offset, spot=spot, days_left=days_left, step=step)
        for offset in range(-STRIKES_EITHER_SIDE, STRIKES_EITHER_SIDE + 1)
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


def _build_row(*, strike: Decimal, spot: Decimal, days_left: int, step: Decimal) -> StrikeRow:
    distance = abs(strike - spot)
    # Time value decays with distance from spot and with days remaining.
    time_value = Decimal(str(round(math.exp(-float(distance / (step * 12))) * 90, 2)))
    time_value *= Decimal(str(round(math.sqrt(days_left / 7), 3)))

    call_intrinsic = max(Decimal(0), spot - strike)
    put_intrinsic = max(Decimal(0), strike - spot)

    moneyness = float((strike - spot) / (step * 10))
    call_oi = int(90_000 * math.exp(-(moneyness**2)) + 5_000)
    # Puts carry more open interest below spot: index hedging is one-sided.
    put_oi = int(110_000 * math.exp(-((moneyness + 0.4) ** 2)) + 5_000)

    return StrikeRow(
        strike=strike,
        call=OptionQuote(
            last_price=(call_intrinsic + time_value).quantize(_CENTS),
            open_interest=call_oi,
            open_interest_change=int(call_oi * 0.04) - 1_500,
            volume=int(call_oi * 0.3),
            implied_volatility=Decimal("12.50"),
            bid=(call_intrinsic + time_value - Decimal("0.5")).quantize(_CENTS),
            ask=(call_intrinsic + time_value + Decimal("0.5")).quantize(_CENTS),
            delta=Decimal(str(round(_delta(moneyness), 4))),
        ),
        put=OptionQuote(
            last_price=(put_intrinsic + time_value).quantize(_CENTS),
            open_interest=put_oi,
            open_interest_change=int(put_oi * 0.03) - 900,
            volume=int(put_oi * 0.28),
            implied_volatility=Decimal("13.20"),
            bid=(put_intrinsic + time_value - Decimal("0.5")).quantize(_CENTS),
            ask=(put_intrinsic + time_value + Decimal("0.5")).quantize(_CENTS),
            delta=Decimal(str(round(_delta(moneyness) - 1, 4))),
        ),
    )


def _delta(moneyness: float) -> float:
    """A logistic curve standing in for N(d1): 0.5 at the money, asymptotic."""
    return 1.0 / (1.0 + math.exp(2.5 * moneyness))
