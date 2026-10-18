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
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import (
    DataSource,
    OptionChain,
    OptionQuote,
    Provenance,
    StrikeRow,
)
from chartnexus.infrastructure.brokers.mock.session_model import (
    LADDER_REACH,
    Leg,
    frame_at,
    lot_size,
    strike_step,
)

STRIKES_EITHER_SIDE = LADDER_REACH
_CENTS = Decimal("0.01")
_SPREAD = Decimal("0.5")

#: Scales the synthetic day change on a leg's premium. Sized so an ATM option
#: moves a few percent over a session and a deep wing barely moves, which is
#: the shape a reader expects — it is not a pricing model and does not claim
#: to be one.
_MOCK_DAY_DRIFT = 0.08

#: Fraction of a leg's traded volume left resting at the touch.
_MOCK_DEPTH_SHARE = 0.015


def build_option_chain(
    instrument: InstrumentSymbol, moment: datetime, expiry: str | None = None
) -> OptionChain:
    frame = frame_at(instrument.value, moment)
    spot = _money(frame.spot)
    step = strike_step(instrument)

    expiries = upcoming_expiries(moment.date())
    resolved = expiry if expiry in expiries else expiries[0]
    term = _term_factors(moment.date(), resolved)

    strikes = tuple(
        _build_row(strike=_money(strike), call=call, put=put, spot=spot, step=step, term=term)
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


@dataclass(frozen=True, slots=True)
class _Term:
    """How a contract differs from the front month, by time to expiry.

    The synthetic book used to be identical for every expiry - only the label
    changed. That made the expiry picker impossible to test against the mock:
    switching to November redrew precisely the same chart, which is exactly what
    a broken picker looks like. It also taught the layout the wrong lesson,
    since a real board never looks like that.

    Three effects, all monotonic in days to expiry and all deliberately crude -
    this is a shape, not a pricing model:

    * **Open interest thins out.** Positioning concentrates in the front month;
      a contract two months out carries a fraction of the near one's book.
    * **Premium grows.** More time, more time value.
    * **Implied volatility rises a little.** A gently upward-sloping term
      structure, which is the usual state.
    """

    oi: float
    premium: float
    iv: float


#: The front month is the reference; everything else is scaled against it.
_NEAR_TERM = _Term(oi=1.0, premium=1.0, iv=1.0)


def _term_factors(today: date, expiry: str) -> _Term:
    try:
        days = max(0, (date.fromisoformat(expiry) - today).days)
    except ValueError:
        return _NEAR_TERM

    # Weeks out, where the front weekly is 0.
    weeks = days / 7.0
    return _Term(
        # Halves roughly every four weeks, with a floor so a far month still
        # has a readable book rather than an empty one.
        oi=max(0.08, 1.0 / (1.0 + 0.45 * weeks)),
        # Premium grows with the square root of time, as option value does.
        premium=math.sqrt(1.0 + weeks),
        iv=1.0 + 0.04 * weeks,
    )


def _build_row(
    *, strike: Decimal, call: Leg, put: Leg, spot: Decimal, step: Decimal, term: _Term
) -> StrikeRow:
    moneyness = float((strike - spot) / (step * 10))
    return StrikeRow(
        strike=strike,
        call=_quote(call, delta=_delta(moneyness), term=term),
        put=_quote(put, delta=_delta(moneyness) - 1, term=term),
    )


def _quote(leg: Leg, *, delta: float, term: _Term = _NEAR_TERM) -> OptionQuote:
    last = _money(leg.ltp * term.premium)
    open_interest = int(leg.oi * term.oi)
    oi_change = int(leg.oi_change * term.oi)
    # The model carries the leg's open interest at the session open but not its
    # premium there, so the leg's own day change is derived from the one thing
    # that is modelled: a premium rises with the option's moneyness drift. It
    # is dressing, like the bid/ask spread beside it, and the chain is stamped
    # MOCK so nothing downstream can mistake it for a traded print.
    previous = _money(leg.ltp * term.premium / (1 + _MOCK_DAY_DRIFT * delta))
    change = (last - previous).quantize(_CENTS)
    return OptionQuote(
        last_price=last,
        open_interest=open_interest,
        # The day change a broker actually reports. This used to be a made-up
        # fraction of the current OI, which the Open Interest service's
        # single-snapshot tier then inverted to "reconstruct" a session open —
        # producing an open that never existed.
        open_interest_change=oi_change,
        volume=int(leg.volume * term.oi),
        implied_volatility=Decimal(str(round(leg.iv * term.iv, 2))),
        bid=(last - _SPREAD).quantize(_CENTS),
        ask=(last + _SPREAD).quantize(_CENTS),
        delta=Decimal(str(round(delta, 4))),
        change=change,
        change_percent=(
            (change / previous * Decimal(100)).quantize(_CENTS) if previous > 0 else None
        ),
        previous_oi=max(0, open_interest - oi_change),
        # Depth scaled off traded volume rather than a constant: a far strike
        # with no volume should look thin on the ladder, because it is.
        bid_qty=_depth(leg, term),
        ask_qty=_depth(leg, term),
    )


def _depth(leg: Leg, term: _Term) -> int:
    """A plausible resting quantity at the touch, in units not lots."""
    return max(0, int(leg.volume * term.oi * _MOCK_DEPTH_SHARE))


def _delta(moneyness: float) -> float:
    """A logistic curve standing in for N(d1): 0.5 at the money, asymptotic."""
    return 1.0 / (1.0 + math.exp(2.5 * moneyness))


def _money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(_CENTS)
