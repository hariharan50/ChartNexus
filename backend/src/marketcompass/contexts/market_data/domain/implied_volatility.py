"""Black-Scholes implied volatility for legs the broker didn't quote.

FYERS' ``options-chain-v3`` response carries no ``iv`` (or any other greek) at
all — every leg comes back with only price, OI and volume. Rather than an ATM
IV that is permanently blank, this back-solves volatility from the same live
inputs the broker *does* give us: last traded price, strike, spot, and time to
expiry.

This is a European, no-dividend Black-Scholes model — the standard
approximation for cash-settled index options — solved with Newton-Raphson and
a bisection fallback for the cases Newton doesn't converge (deep ITM/OTM legs,
or a quote taken seconds before expiry). It is an estimate for display, not a
pricing engine: nothing here should feed an order.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from marketcompass.contexts.market_data.domain.market_data import (
    OptionChain,
    OptionQuote,
    OptionType,
)

# Index options expire at the exchange close, not midnight — using midnight
# would understate time-to-expiry by a full trading session on expiry day.
_EXCHANGE_TZ = ZoneInfo("Asia/Kolkata")
_EXCHANGE_CLOSE = time(15, 30)

# Below this, Black-Scholes is numerically unstable and the "IV" it would
# report is noise, not signal — better to leave the leg blank.
_MIN_YEARS_TO_EXPIRY = 1.0 / (365.0 * 24.0)  # one hour

_NEWTON_ITERATIONS = 30
_NEWTON_TOLERANCE = 1e-6
_MIN_VEGA = 1e-8
"""Below this, a Newton step would divide by (near) zero — hand off to bisection."""
_BISECTION_ITERATIONS = 60
_MIN_VOL, _MAX_VOL = 0.001, 5.0
"""0.1%-500%: wide enough to bracket any real quote without a solver escaping
to a nonsensical extreme."""


def backfill_implied_volatility(
    chain: OptionChain,
    *,
    valuation_time: datetime,
    risk_free_rate: float,
) -> OptionChain:
    """Return ``chain`` with computed IV filling any leg the broker left blank.

    Legs that already carry an ``implied_volatility`` (mock data, or a future
    broker that does supply greeks) are left untouched.
    """
    expiry_date = _parse_iso_date(chain.expiry)
    if expiry_date is None:
        return chain

    years = _years_to_expiry(valuation_time, expiry_date)
    if years < _MIN_YEARS_TO_EXPIRY:
        return chain

    spot = float(chain.spot_price)
    if spot <= 0:
        return chain

    def enriched(strike: Decimal, quote: OptionQuote | None, option_type: OptionType) -> OptionQuote | None:
        if quote is None or quote.implied_volatility is not None:
            return quote
        price = float(quote.last_price)
        if price <= 0:
            return quote
        iv = _solve_implied_volatility(
            price=price,
            spot=spot,
            strike=float(strike),
            years=years,
            rate=risk_free_rate,
            is_call=option_type is OptionType.CALL,
        )
        if iv is None:
            return quote
        # Stored as a percentage (13.2 meaning 13.2%), matching every other
        # implied_volatility value in the system (mock data, the fixture).
        return replace(quote, implied_volatility=Decimal(str(round(iv * 100, 2))))

    new_strikes = tuple(
        replace(
            row,
            call=enriched(row.strike, row.call, OptionType.CALL),
            put=enriched(row.strike, row.put, OptionType.PUT),
        )
        for row in chain.strikes
    )
    return replace(chain, strikes=new_strikes)


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _years_to_expiry(valuation_time: datetime, expiry_date: date) -> float:
    expiry_instant = datetime.combine(expiry_date, _EXCHANGE_CLOSE, tzinfo=_EXCHANGE_TZ)
    aware_valuation = (
        valuation_time if valuation_time.tzinfo is not None else valuation_time.astimezone(_EXCHANGE_TZ)
    )
    remaining: timedelta = expiry_instant - aware_valuation
    return remaining.total_seconds() / (365.0 * 24.0 * 3600.0)


def _black_scholes_price(*, spot: float, strike: float, years: float, rate: float, vol: float, is_call: bool) -> float:
    if vol <= 0 or years <= 0:
        return max(0.0, (spot - strike) if is_call else (strike - spot))
    sqrt_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    discounted_strike = strike * math.exp(-rate * years)
    if is_call:
        return spot * _norm_cdf(d1) - discounted_strike * _norm_cdf(d2)
    return discounted_strike * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def _vega(*, spot: float, strike: float, years: float, rate: float, vol: float) -> float:
    if vol <= 0 or years <= 0:
        return 0.0
    sqrt_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / (vol * sqrt_t)
    return spot * sqrt_t * _norm_pdf(d1)


def _solve_implied_volatility(
    *, price: float, spot: float, strike: float, years: float, rate: float, is_call: bool
) -> float | None:
    # A quote priced below intrinsic value (stale bid/ask, a fat-fingered
    # print) has no valid implied volatility — any solver would either fail to
    # converge or return garbage, so refuse rather than guess.
    intrinsic = max(0.0, (spot - strike) if is_call else (strike - spot))
    if price < intrinsic:
        return None

    vol = 0.3  # 30% is a reasonable starting guess for index options.
    for _ in range(_NEWTON_ITERATIONS):
        model_price = _black_scholes_price(
            spot=spot, strike=strike, years=years, rate=rate, vol=vol, is_call=is_call
        )
        diff = model_price - price
        if abs(diff) < _NEWTON_TOLERANCE:
            return vol
        vega = _vega(spot=spot, strike=strike, years=years, rate=rate, vol=vol)
        if vega < _MIN_VEGA:
            break
        vol -= diff / vega
        if vol <= _MIN_VOL or vol >= _MAX_VOL:
            break
    else:
        return vol if _MIN_VOL < vol < _MAX_VOL else _bisect_implied_volatility(
            price=price, spot=spot, strike=strike, years=years, rate=rate, is_call=is_call
        )

    return _bisect_implied_volatility(
        price=price, spot=spot, strike=strike, years=years, rate=rate, is_call=is_call
    )


def _bisect_implied_volatility(
    *, price: float, spot: float, strike: float, years: float, rate: float, is_call: bool
) -> float | None:
    low, high = _MIN_VOL, _MAX_VOL
    price_at_low = _black_scholes_price(spot=spot, strike=strike, years=years, rate=rate, vol=low, is_call=is_call)
    price_at_high = _black_scholes_price(spot=spot, strike=strike, years=years, rate=rate, vol=high, is_call=is_call)
    if not (price_at_low <= price <= price_at_high):
        return None  # Not bracketed — no volatility in range reproduces this price.

    for _ in range(_BISECTION_ITERATIONS):
        mid = (low + high) / 2
        model_price = _black_scholes_price(spot=spot, strike=strike, years=years, rate=rate, vol=mid, is_call=is_call)
        if abs(model_price - price) < _NEWTON_TOLERANCE:
            return mid
        if model_price < price:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def atm_implied_volatility(chain: OptionChain) -> Decimal | None:
    """The reading shown as "ATM IV": the CE/PE average at the nearest strike.

    Averages both sides when both are quoted (illiquid far-dated contracts
    sometimes carry only one side); either side alone is used when that is all
    there is.
    """
    atm = chain.atm_strike
    if atm is None:
        return None
    row = next((r for r in chain.strikes if r.strike == atm), None)
    if row is None:
        return None
    values = [
        q.implied_volatility
        for q in (row.call, row.put)
        if q is not None and q.implied_volatility is not None
    ]
    if not values:
        return None
    return sum(values, Decimal(0)) / len(values)
