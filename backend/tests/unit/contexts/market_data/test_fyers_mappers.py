"""FYERS response parsing.

These are regression tests for two specific defects the source architecture
documents: a camelCase parser collapsing every contract onto strike 0, and the
underlying leg being treated as an option.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import DataSource
from chartnexus.infrastructure.brokers.fyers.option_chain_mapper import (
    _normalise_date,
    to_option_chain,
)
from chartnexus.infrastructure.brokers.fyers.quote_mapper import to_quote
from chartnexus.infrastructure.brokers.fyers.symbol_mapper import (
    from_broker_symbol,
    to_broker_symbol,
)
from chartnexus.shared_kernel.domain.errors import UpstreamError

pytestmark = pytest.mark.unit

NOW = datetime(2026, 7, 24, 11, 20, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "fyers"


@pytest.fixture(scope="module")
def chain_payload() -> dict[str, Any]:
    return json.loads((FIXTURES / "option_chain_nifty.json").read_text(encoding="utf-8"))


# --- symbols ---------------------------------------------------------------


def test_symbols_map_both_ways() -> None:
    assert to_broker_symbol(InstrumentSymbol("NIFTY")) == "NSE:NIFTY50-INDEX"
    assert to_broker_symbol(InstrumentSymbol("BANKNIFTY")) == "NSE:NIFTYBANK-INDEX"
    assert to_broker_symbol(InstrumentSymbol("SENSEX")) == "BSE:SENSEX-INDEX"
    # Equality, not identity: an instrument symbol is a value object now, not
    # an interned enum member, so two "NIFTY"s are equal but not the same object.
    assert from_broker_symbol("NSE:NIFTY50-INDEX") == InstrumentSymbol("NIFTY")
    assert from_broker_symbol("NSE:SOMETHING-ELSE") is None


# --- quotes ----------------------------------------------------------------


def test_quote_is_parsed() -> None:
    payload = {
        "s": "ok",
        "d": [
            {
                "n": "NSE:NIFTY50-INDEX",
                "v": {
                    "lp": 24123.45,
                    "ch": -18.2,
                    "chp": -0.42,
                    "open_price": 24180.0,
                    "prev_close_price": 24141.65,
                },
            }
        ],
    }

    quote = to_quote(payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)

    assert quote.price == Decimal("24123.45")
    assert quote.change_percent == Decimal("-0.42")
    assert quote.day_open == Decimal("24180.0")
    assert quote.previous_close == Decimal("24141.65")
    assert quote.provenance.source is DataSource.LIVE


def test_quote_accepts_the_abbreviated_open_and_previous_close_keys() -> None:
    """The depth payload abbreviates what the quotes endpoint spells out."""
    payload = {
        "s": "ok",
        "d": [{"n": "NSE:NIFTY50-INDEX", "v": {"lp": 24123.45, "o": 24180, "pc": 24141.65}}],
    }

    quote = to_quote(payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)

    assert quote.day_open == Decimal("24180")
    assert quote.previous_close == Decimal("24141.65")


def test_a_quote_without_an_open_stays_missing_rather_than_guessing() -> None:
    """A gap read off a fabricated open would be worse than no gap at all."""
    payload = {"s": "ok", "d": [{"n": "NSE:NIFTY50-INDEX", "v": {"lp": 24123.45}}]}

    quote = to_quote(payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)

    assert quote.day_open is None
    assert quote.previous_close is None


def test_quote_without_a_price_is_rejected() -> None:
    """Better to fail over to cached data than to render a zero as a price."""
    payload = {"s": "ok", "d": [{"n": "NSE:NIFTY50-INDEX", "v": {}}]}

    with pytest.raises(UpstreamError):
        to_quote(payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)


def test_empty_quote_response_is_rejected() -> None:
    with pytest.raises(UpstreamError):
        to_quote({"s": "ok", "d": []}, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)


# --- option chain ----------------------------------------------------------


def test_chain_does_not_collapse_onto_strike_zero(chain_payload: dict[str, Any]) -> None:
    """The camelCase-parser bug: every contract landing on strike 0."""
    chain = to_option_chain(chain_payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)

    strikes = [row.strike for row in chain.strikes]
    assert strikes == [Decimal(24050), Decimal(24100), Decimal(24150)]
    assert Decimal(0) not in strikes


def test_underlying_leg_supplies_spot_change_and_future(chain_payload: dict[str, Any]) -> None:
    """strike_price == -1 is the index, not a tradeable strike."""
    chain = to_option_chain(chain_payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)

    assert chain.spot_price == Decimal("24123.45")
    assert chain.change_percent == Decimal("-0.42")
    assert chain.future_price == Decimal("24145.0")
    # And it must not have become a strike.
    assert Decimal(-1) not in [row.strike for row in chain.strikes]


def test_both_legs_are_parsed_with_snake_case_keys(chain_payload: dict[str, Any]) -> None:
    chain = to_option_chain(chain_payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)
    atm = next(row for row in chain.strikes if row.strike == Decimal(24100))

    assert atm.call is not None
    assert atm.call.last_price == Decimal("150.25")
    assert atm.call.open_interest == 123456
    assert atm.call.open_interest_change == 6400  # `oich`, not `oiChange`
    assert atm.call.delta == Decimal("0.52")

    assert atm.put is not None
    assert atm.put.open_interest_change == -2100


def test_a_strike_quoted_on_one_side_only_keeps_the_other_side_none(
    chain_payload: dict[str, Any],
) -> None:
    """Illiquid strikes are one-sided; inventing a zero would corrupt PCR."""
    chain = to_option_chain(chain_payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)
    row = next(row for row in chain.strikes if row.strike == Decimal(24050))

    assert row.call is not None
    assert row.put is None


def test_expiries_come_from_the_broker(chain_payload: dict[str, Any]) -> None:
    chain = to_option_chain(chain_payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)

    assert chain.expiries == ("2026-07-30", "2026-08-06", "2026-08-27")
    assert chain.expiry == "2026-07-30"
    assert chain.lot_size == 75


def test_pcr_and_atm_are_computed_from_the_chain(chain_payload: dict[str, Any]) -> None:
    chain = to_option_chain(chain_payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)

    # PE OI 115000+117000 over CE OI 123456+71544+60000
    expected = (Decimal(232000) / Decimal(255000)).quantize(Decimal("0.0001"))
    assert chain.put_call_ratio == expected
    # Spot 24123.45 is nearest the 24100 strike.
    assert chain.atm_strike == Decimal(24100)


def test_pcr_is_undefined_rather_than_zero_without_call_interest() -> None:
    payload = {
        "s": "ok",
        "data": {
            "expiryData": [{"date": "30-07-2026"}],
            "optionsChain": [
                {"strike_price": -1, "ltp": 100},
                {"strike_price": 100, "option_type": "PE", "ltp": 5, "oi": 10},
            ],
        },
    }
    chain = to_option_chain(payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)

    assert chain.put_call_ratio is None


def test_chain_without_strikes_is_rejected() -> None:
    payload = {"s": "ok", "data": {"optionsChain": [{"strike_price": -1, "ltp": 100}]}}

    with pytest.raises(UpstreamError):
        to_option_chain(payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)


def test_chain_without_a_spot_price_is_rejected() -> None:
    payload = {
        "s": "ok",
        "data": {"optionsChain": [{"strike_price": 100, "option_type": "CE", "ltp": 5, "oi": 1}]},
    }

    with pytest.raises(UpstreamError):
        to_option_chain(payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)


def test_missing_underlying_ltp_is_rejected_rather_than_reading_india_vix() -> None:
    """Regression: a missing underlying ``ltp`` must never fall back to
    ``indiavixData.ltp`` — VIX (~10-20) is not a stand-in for an index's spot
    price (~20,000+), and silently swapping one in corrupts the derived ATM
    strike (and, downstream, ATM IV) rather than surfacing a clear error."""
    payload = {
        "s": "ok",
        "data": {
            "indiavixData": {"ltp": 13.42, "ltpchp": -1.2},
            "optionsChain": [
                {"strike_price": -1},
                {"strike_price": 100, "option_type": "CE", "ltp": 5, "oi": 1},
            ],
        },
    }

    with pytest.raises(UpstreamError):
        to_option_chain(payload, instrument=InstrumentSymbol("NIFTY"), fetched_at=NOW)


# --- expiry normalisation --------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("30-07-2026", "2026-07-30"),
        ("2026-07-30", "2026-07-30"),
        ("30-Jul-2026", "2026-07-30"),
        ("30-July-2026", "2026-07-30"),
        ("1785340800", "2026-07-29"),
    ],
)
def test_expiry_formats_normalise_to_iso(raw: str, expected: str) -> None:
    """The epoch case is resolved in IST: NSE expiries are exchange-local dates."""
    assert _normalise_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "not-a-date", "32-13-2026", "5", None])
def test_unparseable_expiries_are_dropped_not_guessed(raw: str | None) -> None:
    """A wrong expiry silently prices the wrong contract."""
    assert _normalise_date(raw) is None
