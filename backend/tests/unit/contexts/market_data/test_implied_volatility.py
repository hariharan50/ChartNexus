"""Black-Scholes IV back-solving.

FYERS returns no greeks at all, so ``backfill_implied_volatility`` is the only
source of ATM IV on live data. These tests pin the numerical solver (round-trip
a known volatility through the pricer and back) and the policy choices around
it (never overwrite a broker-supplied IV, never invent one from a bad quote).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from chartnexus.contexts.market_data.domain.implied_volatility import (
    _black_scholes_price,
    _solve_implied_volatility,
    atm_implied_volatility,
    backfill_implied_volatility,
)
from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import (
    DataSource,
    OptionChain,
    OptionQuote,
    Provenance,
    StrikeRow,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 7, 24, 6, 0, tzinfo=UTC)  # ~11:30 IST
FAR_EXPIRY = "2026-08-27"


def _chain(
    strikes: tuple[StrikeRow, ...], *, expiry: str = FAR_EXPIRY, spot: str = "24600"
) -> OptionChain:
    return OptionChain(
        instrument=InstrumentSymbol("NIFTY"),
        expiry=expiry,
        spot_price=Decimal(spot),
        strikes=strikes,
        provenance=Provenance(source=DataSource.LIVE, fetched_at=NOW),
    )


def _quote(price: str, *, iv: str | None = None) -> OptionQuote:
    return OptionQuote(
        last_price=Decimal(price),
        open_interest=1,
        open_interest_change=0,
        volume=1,
        implied_volatility=Decimal(iv) if iv is not None else None,
    )


# --- the solver itself -------------------------------------------------------


@pytest.mark.parametrize("true_vol", [0.10, 0.15, 0.25, 0.40])
@pytest.mark.parametrize("is_call", [True, False])
def test_solver_recovers_a_known_volatility(true_vol: float, is_call: bool) -> None:
    spot, strike, years, rate = 24600.0, 24600.0, 30 / 365, 0.07
    price = _black_scholes_price(
        spot=spot, strike=strike, years=years, rate=rate, vol=true_vol, is_call=is_call
    )

    solved = _solve_implied_volatility(
        price=price, spot=spot, strike=strike, years=years, rate=rate, is_call=is_call
    )

    assert solved is not None
    assert solved == pytest.approx(true_vol, abs=1e-3)


def test_solver_rejects_a_price_below_intrinsic_value() -> None:
    # A 24000 CE with spot at 24600 has intrinsic value 600; a quote of 10 is
    # not reproducible by any Black-Scholes volatility and must not be guessed.
    solved = _solve_implied_volatility(
        price=10.0, spot=24600.0, strike=24000.0, years=30 / 365, rate=0.07, is_call=True
    )

    assert solved is None


# --- chain-level backfill ----------------------------------------------------


def test_backfill_computes_iv_for_legs_the_broker_left_blank() -> None:
    chain = _chain((StrikeRow(strike=Decimal("24600"), call=_quote("250"), put=_quote("240")),))

    filled = backfill_implied_volatility(chain, valuation_time=NOW, risk_free_rate=0.07)

    assert filled.strikes[0].call is not None
    assert filled.strikes[0].call.implied_volatility is not None
    assert filled.strikes[0].put is not None
    assert filled.strikes[0].put.implied_volatility is not None


def test_backfill_never_overwrites_a_broker_supplied_iv() -> None:
    chain = _chain((StrikeRow(strike=Decimal("24600"), call=_quote("250", iv="12.5")),))

    filled = backfill_implied_volatility(chain, valuation_time=NOW, risk_free_rate=0.07)

    assert filled.strikes[0].call is not None
    assert filled.strikes[0].call.implied_volatility == Decimal("12.5")


def test_backfill_leaves_a_leg_blank_rather_than_guessing_from_a_bad_price() -> None:
    # 10 is below the 24000 CE's intrinsic value against a 24600 spot.
    chain = _chain((StrikeRow(strike=Decimal("24000"), call=_quote("10")),))

    filled = backfill_implied_volatility(chain, valuation_time=NOW, risk_free_rate=0.07)

    assert filled.strikes[0].call is not None
    assert filled.strikes[0].call.implied_volatility is None


def test_backfill_is_a_noop_on_or_after_expiry() -> None:
    chain = _chain(
        (StrikeRow(strike=Decimal("24600"), call=_quote("250")),),
        expiry="2026-07-24",
    )
    # NOW is 06:00 UTC == 11:30 IST, well before the 15:30 IST close, so this
    # exercises a chain that is genuinely past a *different* day's close.
    past_close = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)  # 17:30 IST

    filled = backfill_implied_volatility(chain, valuation_time=past_close, risk_free_rate=0.07)

    assert filled.strikes[0].call is not None
    assert filled.strikes[0].call.implied_volatility is None


def test_backfill_returns_chain_unchanged_when_expiry_is_unparseable() -> None:
    chain = _chain((StrikeRow(strike=Decimal("24600"), call=_quote("250")),), expiry="not-a-date")

    filled = backfill_implied_volatility(chain, valuation_time=NOW, risk_free_rate=0.07)

    assert filled is chain


# --- ATM IV (the "ATM IV" tile, and the input to IV Percentile) -------------


def test_atm_iv_averages_both_sides_when_both_are_quoted() -> None:
    chain = _chain(
        (
            StrikeRow(
                strike=Decimal("24600"), call=_quote("250", iv="12"), put=_quote("240", iv="14")
            ),
        )
    )

    assert atm_implied_volatility(chain) == Decimal("13")


def test_atm_iv_uses_whichever_side_is_quoted_when_only_one_is() -> None:
    chain = _chain((StrikeRow(strike=Decimal("24600"), call=_quote("250", iv="12")),))

    assert atm_implied_volatility(chain) == Decimal("12")


def test_atm_iv_is_none_without_an_atm_strike() -> None:
    chain = _chain(())

    assert atm_implied_volatility(chain) is None
