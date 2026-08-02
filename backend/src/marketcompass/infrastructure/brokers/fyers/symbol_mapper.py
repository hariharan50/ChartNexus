"""Canonical instrument names to FYERS symbols.

The only place broker symbol strings appear. Everything above this speaks
``InstrumentSymbol``.
"""

from __future__ import annotations

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.shared_kernel.domain.errors import ValidationError

_TO_FYERS: dict[InstrumentSymbol, str] = {
    InstrumentSymbol.NIFTY: "NSE:NIFTY50-INDEX",
    InstrumentSymbol.BANKNIFTY: "NSE:NIFTYBANK-INDEX",
    InstrumentSymbol.SENSEX: "BSE:SENSEX-INDEX",
}

_FROM_FYERS: dict[str, InstrumentSymbol] = {value: key for key, value in _TO_FYERS.items()}


def to_broker_symbol(instrument: InstrumentSymbol) -> str:
    try:
        return _TO_FYERS[instrument]
    except KeyError as exc:
        raise ValidationError(
            f"{instrument.value} is not available from this broker.", field="instrument"
        ) from exc


def from_broker_symbol(symbol: str) -> InstrumentSymbol | None:
    """Reverse lookup. Returns None for anything we do not track."""
    return _FROM_FYERS.get(symbol.strip().upper())


def supported_instruments() -> tuple[InstrumentSymbol, ...]:
    return tuple(_TO_FYERS)
