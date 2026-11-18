"""Zerodha's instrument dump: parse, validate, and the lookups Kite needs.

Kite has no option-chain endpoint and streams by integer token, so every Kite
read starts here:

* **spot** — the ``EXCHANGE:TRADINGSYMBOL`` to quote for a canonical symbol;
* **futures** — an underlying's listed futures, nearest first, so ``series=0``
  is the front month (the same index convention as the FYERS adapter);
* **options** — every CE/PE for one expiry, from which a chain is assembled;
* **tokens** — for the WebSocket and the historical endpoint.

Canonical → Kite naming: the ChartNexus catalog's ``futures_root`` is
exactly the ``name`` Zerodha gives an underlying's derivatives (``NIFTY``,
``BANKNIFTY``, ``RELIANCE``), and a stock's spot is ``NSE:<symbol>``. Only
index *spots* need a table, because Zerodha names them for display
(``NIFTY 50``, ``NIFTY BANK``).
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

#: Canonical index symbol → (exchange, Zerodha's index tradingsymbol).
INDEX_SPOTS: dict[str, tuple[str, str]] = {
    "NIFTY": ("NSE", "NIFTY 50"),
    "BANKNIFTY": ("NSE", "NIFTY BANK"),
    "FINNIFTY": ("NSE", "NIFTY FIN SERVICE"),
    "MIDCPNIFTY": ("NSE", "NIFTY MID SELECT"),
    "NIFTYNXT50": ("NSE", "NIFTY NEXT 50"),
    "SENSEX": ("BSE", "SENSEX"),
    "BANKEX": ("BSE", "BANKEX"),
    "INDIAVIX": ("NSE", "INDIA VIX"),
}

#: The derivative exchanges Kite lists F&O on.
DERIVATIVE_EXCHANGES = frozenset({"NFO", "BFO"})

#: A filtered dump smaller than this is a truncated download, not a quiet day.
#: NFO alone lists tens of thousands of contracts.
MIN_ROWS = 5_000
REQUIRED_EXCHANGES = frozenset({"NFO", "BFO"})

_OPTION_TYPES = frozenset({"CE", "PE"})
_FUTURE = "FUT"


@dataclass(frozen=True, slots=True)
class KiteInstrument:
    instrument_token: int
    exchange: str
    segment: str
    tradingsymbol: str
    name: str
    instrument_type: str
    expiry: date | None
    strike: Decimal | None
    lot_size: int
    tick_size: Decimal

    @property
    def quote_key(self) -> str:
        """How ``/quote`` names it: ``EXCHANGE:TRADINGSYMBOL``."""
        return f"{self.exchange}:{self.tradingsymbol}"

    @property
    def is_option(self) -> bool:
        return self.instrument_type in _OPTION_TYPES

    @property
    def is_future(self) -> bool:
        return self.instrument_type == _FUTURE


class InstrumentDumpError(ValueError):
    """The dump failed validation; yesterday's catalog stays in place."""


def parse_dump(
    text: str, *, equities: Iterable[str] = (), index_names: Iterable[str] = ()
) -> list[KiteInstrument]:
    """Parse and filter the CSV to what ChartNexus can use.

    Kept: index spots (``segment == "INDICES"``) we name, equities in the
    ChartNexus catalog, and every NFO/BFO future and option. Dropped: currency,
    commodity, bonds, ETFs and the long tail of equities nobody here charts.
    """
    wanted_equities = {symbol.upper() for symbol in equities}
    wanted_indices = {name.upper() for _, name in INDEX_SPOTS.values()} | {
        name.upper() for name in index_names
    }

    rows: list[KiteInstrument] = []
    for raw in csv.DictReader(io.StringIO(text)):
        exchange = (raw.get("exchange") or "").strip().upper()
        segment = (raw.get("segment") or "").strip().upper()
        symbol = (raw.get("tradingsymbol") or "").strip()
        kind = (raw.get("instrument_type") or "").strip().upper()

        if exchange in DERIVATIVE_EXCHANGES:
            if kind not in _OPTION_TYPES and kind != _FUTURE:
                continue
        elif segment == "INDICES":
            if symbol.upper() not in wanted_indices:
                continue
        elif exchange in {"NSE", "BSE"} and kind == "EQ":
            if symbol.upper() not in wanted_equities:
                continue
        else:
            continue

        parsed = _row(raw, exchange=exchange, segment=segment, symbol=symbol, kind=kind)
        if parsed is not None:
            rows.append(parsed)
    return rows


def validate(rows: list[KiteInstrument]) -> None:
    """Refuse a dump that would make the catalog worse than yesterday's."""
    if len(rows) < MIN_ROWS:
        msg = f"instrument dump has {len(rows)} usable rows; expected at least {MIN_ROWS}"
        raise InstrumentDumpError(msg)
    present = Counter(row.exchange for row in rows)
    missing = sorted(REQUIRED_EXCHANGES - present.keys())
    if missing:
        msg = f"instrument dump is missing {', '.join(missing)}"
        raise InstrumentDumpError(msg)
    if not any(row.segment == "INDICES" for row in rows):
        raise InstrumentDumpError("instrument dump lists no index spots")


def spot_key(symbol: str, exchange: str) -> tuple[str, str]:
    """``(exchange, tradingsymbol)`` of a canonical symbol's spot.

    ``exchange`` is the catalog's listing exchange, used for equities.
    """
    canonical = symbol.upper()
    if canonical in INDEX_SPOTS:
        return INDEX_SPOTS[canonical]
    return (exchange.upper() or "NSE", canonical)


def derivative_exchange(listing_exchange: str) -> str:
    """BSE underlyings (SENSEX, BANKEX) trade F&O on BFO; everything else on NFO."""
    return "BFO" if listing_exchange.upper() == "BSE" else "NFO"


def _row(
    raw: dict[str, str], *, exchange: str, segment: str, symbol: str, kind: str
) -> KiteInstrument | None:
    try:
        token = int(raw.get("instrument_token") or "")
    except ValueError:
        return None
    return KiteInstrument(
        instrument_token=token,
        exchange=exchange,
        segment=segment,
        tradingsymbol=symbol,
        # Zerodha quotes some names ("\"NIFTY\""); the CSV reader keeps the quotes.
        name=(raw.get("name") or "").strip().strip('"').upper(),
        instrument_type=kind,
        expiry=_date(raw.get("expiry")),
        strike=_decimal(raw.get("strike")),
        lot_size=_int(raw.get("lot_size"), default=1),
        tick_size=_decimal(raw.get("tick_size")) or Decimal("0.05"),
    )


def _date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _decimal(value: str | None) -> Decimal | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number else None


def _int(value: str | None, *, default: int) -> int:
    try:
        return int(float((value or "").strip()))
    except ValueError:
        return default
