"""Canonical instrument names to FYERS symbols.

The only place broker symbol strings appear. Everything above this speaks
``InstrumentSymbol``.

This used to be a three-entry dict. It is now a catalog lookup, because the
mapping is not one shape: an index is quoted ``NSE:NIFTY50-INDEX`` while a
company is quoted ``NSE:RELIANCE-EQ``, and the index root is not even derivable
from the canonical name (``BANKNIFTY`` maps to ``NIFTYBANK``). Those strings
come straight from the exchange's own symbol master, so nobody has to maintain
two hundred of them by hand.
"""

from __future__ import annotations

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.infrastructure.catalog import registry


def to_broker_symbol(instrument: InstrumentSymbol) -> str:
    """The broker's symbol for this instrument's spot/underlying price."""
    return registry.current().get(instrument).spot_symbol


def from_broker_symbol(symbol: str) -> InstrumentSymbol | None:
    """Reverse lookup. Returns None for anything we do not track."""
    needle = symbol.strip().upper()
    for instrument in registry.current().all():
        if instrument.spot_symbol.upper() == needle:
            return InstrumentSymbol(instrument.symbol)
    return None
