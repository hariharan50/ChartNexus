"""The open instrument symbol, and the registry that decides what exists.

``InstrumentSymbol`` stopped being a three-member enum when the app grew past
three instruments. These tests pin the split that replaced it: the type
guarantees *shape*, the catalog registry guarantees *existence*.
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs, quote, unquote

import pytest

from marketcompass.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.infrastructure.brokers.fyers.symbol_mapper import to_broker_symbol
from marketcompass.infrastructure.catalog import registry
from marketcompass.shared_kernel.domain.errors import ValidationError

pytestmark = pytest.mark.unit


# -- shape ------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["NIFTY", " nifty ", "Nifty"])
def test_parsing_normalises(raw: str) -> None:
    assert InstrumentSymbol(raw) == "NIFTY"


@pytest.mark.parametrize("raw", ["M&M", "GVT&D", "BAJAJ-AUTO", "NAM-INDIA", "360ONE"])
def test_real_tickers_are_accepted(raw: str) -> None:
    """Ampersands, hyphens and leading digits all occur in the real universe."""
    assert InstrumentSymbol(raw) == raw


@pytest.mark.parametrize("raw", ["", "   ", None, "N" * 21, "DROP TABLE", "NIF/TY", "a;b"])
def test_malformed_symbols_are_rejected(raw: object) -> None:
    with pytest.raises(ValidationError):
        InstrumentSymbol(raw)


def test_it_is_a_string() -> None:
    """Every symbol column, cache key and log field already treats it as text."""
    symbol = InstrumentSymbol("RELIANCE")

    assert isinstance(symbol, str)
    assert f"{symbol}" == "RELIANCE"
    assert symbol.value == "RELIANCE"
    assert {symbol: 1}["RELIANCE"] == 1


def test_an_unknown_but_well_formed_symbol_parses() -> None:
    """Shape is not existence.

    ``parse`` deliberately accepts this; the catalog is what rejects it, at the
    point where something actually needs the row.
    """
    assert InstrumentSymbol("NOTLISTED") == "NOTLISTED"


# -- existence --------------------------------------------------------------


def _instrument(symbol: str, spot: str) -> Instrument:
    return Instrument(
        symbol=symbol,
        kind=InstrumentKind.STOCK,
        name=symbol,
        exchange="NSE",
        lot_size=1,
        tick_size=Decimal("0.05"),
        spot_symbol=spot,
        futures_root=symbol,
    )


def test_the_registry_rejects_an_instrument_it_does_not_hold() -> None:
    with pytest.raises(ValidationError, match="not a tradeable instrument"):
        to_broker_symbol(InstrumentSymbol("NOTLISTED"))


def test_lookup_is_case_and_whitespace_insensitive() -> None:
    with registry.installed([_instrument("RELIANCE", "NSE:RELIANCE-EQ")]) as live:
        assert live.get(" reliance ").symbol == "RELIANCE"
        assert "RELIANCE" in live
        assert live.find("NOPE") is None


def test_symbols_are_ordered_indices_first_then_alphabetically() -> None:
    rows = [
        _instrument("TCS", "NSE:TCS-EQ"),
        _instrument("RELIANCE", "NSE:RELIANCE-EQ"),
        Instrument(
            symbol="NIFTY",
            kind=InstrumentKind.INDEX,
            name="NIFTY50",
            exchange="NSE",
            lot_size=75,
            tick_size=Decimal("0.05"),
            spot_symbol="NSE:NIFTY50-INDEX",
            futures_root="NIFTY",
        ),
    ]
    with registry.installed(rows) as live:
        assert live.symbols() == ("NIFTY", "RELIANCE", "TCS")
        assert live.symbols(kind=InstrumentKind.INDEX) == ("NIFTY",)


def test_installing_a_registry_restores_the_previous_one() -> None:
    """The suite-wide fixture must survive a test that scopes its own."""
    before = to_broker_symbol(InstrumentSymbol("NIFTY"))

    with registry.installed([_instrument("ONLYTHIS", "NSE:ONLYTHIS-EQ")]):
        assert to_broker_symbol(InstrumentSymbol("ONLYTHIS")) == "NSE:ONLYTHIS-EQ"

    assert to_broker_symbol(InstrumentSymbol("NIFTY")) == before


# -- the ampersand hazard ---------------------------------------------------


def test_an_ampersand_ticker_survives_url_encoding() -> None:
    """``M&M`` is a real ticker and the market-data routes take the instrument
    as a *query* parameter, so it has to be percent-encoded by the caller."""
    encoded = quote("M&M", safe="")

    assert encoded == "M%26M"
    assert InstrumentSymbol(unquote(encoded)) == "M&M"


def test_an_unencoded_ampersand_fails_loudly_rather_than_silently() -> None:
    """The trap this pins down.

    Sent unencoded, ``?instrument=M&M`` is parsed by any conforming server as
    ``instrument=M`` plus a stray key — the symbol is truncated. ``M`` is a
    perfectly well-formed symbol, so shape validation cannot catch it; what
    catches it is the catalog, which has no such instrument. The request then
    fails with a clear message instead of quietly returning data for the wrong
    contract.
    """
    parsed = parse_qs("instrument=M&M")
    assert parsed["instrument"] == ["M"]  # the truncation

    with pytest.raises(ValidationError, match="not a tradeable instrument"):
        to_broker_symbol(InstrumentSymbol(parsed["instrument"][0]))
