"""Which symbols the capture loop archives.

The default is indices only, and a stock left out of it is not a cosmetic gap:
nothing archived means every Options Lab series for that symbol falls back to
the two-point "open vs now" proxy, which draws as a straight line across the
session. ``"*"`` is the switch that opts the whole F&O universe in.
"""

from __future__ import annotations

from decimal import Decimal

from chartnexus.bootstrap.settings import MarketSettings, Settings
from chartnexus.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)
from chartnexus.entrypoints.ingest_runtime import ingest_symbols
from chartnexus.infrastructure.catalog import registry


def _instrument(symbol: str, kind: InstrumentKind) -> Instrument:
    suffix = "INDEX" if kind is InstrumentKind.INDEX else "EQ"
    return Instrument(
        symbol=symbol,
        kind=kind,
        name=symbol.title(),
        exchange="NSE",
        lot_size=50,
        tick_size=Decimal("0.05"),
        spot_symbol=f"NSE:{symbol}-{suffix}",
        futures_root=symbol,
    )


CATALOG = (
    _instrument("NIFTY", InstrumentKind.INDEX),
    _instrument("BANKNIFTY", InstrumentKind.INDEX),
    _instrument("ITC", InstrumentKind.STOCK),
    _instrument("RELIANCE", InstrumentKind.STOCK),
)


def _settings(*symbols: str) -> Settings:
    return Settings(market=MarketSettings(ingest_symbols=symbols))


def test_defaults_to_indices_only() -> None:
    with registry.installed(CATALOG):
        assert ingest_symbols(_settings()) == ("BANKNIFTY", "NIFTY")


def test_star_covers_every_instrument() -> None:
    """The whole universe, stocks included — the reason a stock can chart at all."""
    with registry.installed(CATALOG):
        assert ingest_symbols(_settings("*")) == (
            "BANKNIFTY",
            "NIFTY",
            "ITC",
            "RELIANCE",
        )


def test_explicit_list_replaces_rather_than_extends() -> None:
    """The trap: naming one stock silently drops every index."""
    with registry.installed(CATALOG):
        assert ingest_symbols(_settings("ITC")) == ("ITC",)


def test_star_is_resolved_per_call() -> None:
    """A catalog refresh is picked up without a restart."""
    settings = _settings("*")
    with registry.installed(CATALOG):
        assert "RELIANCE" in ingest_symbols(settings)
    with registry.installed(CATALOG[:1]):
        assert ingest_symbols(settings) == ("NIFTY",)
