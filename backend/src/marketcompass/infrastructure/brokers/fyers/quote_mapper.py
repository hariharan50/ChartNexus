"""FYERS quote payloads to canonical quotes.

Shape of a quotes response::

    {"s": "ok", "d": [{"n": "NSE:NIFTY50-INDEX", "v": {"lp": 24123.45, ...}}]}

``lp`` is last price, ``ch`` absolute change, ``chp`` percent change.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    DataSource,
    Provenance,
    Quote,
)
from marketcompass.shared_kernel.domain.errors import UpstreamError


def to_quote(
    payload: dict[str, Any], *, instrument: InstrumentSymbol, fetched_at: datetime
) -> Quote:
    values = _first_quote_values(payload)

    price = _decimal(values.get("lp"))
    if price is None:
        # A quote without a last price is not a quote. Raising here lets the
        # caller fall back to real cached data instead of rendering a zero.
        raise UpstreamError("fyers", "The broker returned a quote with no price.")

    return Quote(
        instrument=instrument,
        price=price,
        change=_decimal(values.get("ch")),
        change_percent=_decimal(values.get("chp")),
        # Same key fallbacks the futures mapper already uses: the quotes
        # endpoint spells these out, the depth payload abbreviates them.
        day_open=_decimal(values.get("open_price") or values.get("o")),
        previous_close=_decimal(values.get("prev_close_price") or values.get("pc")),
        provenance=Provenance(source=DataSource.LIVE, fetched_at=fetched_at),
    )


def _first_quote_values(payload: dict[str, Any]) -> dict[str, Any]:
    entries = payload.get("d")
    if not isinstance(entries, list) or not entries:
        raise UpstreamError("fyers", "The broker returned no quote data.")

    first = entries[0]
    values = first.get("v") if isinstance(first, dict) else None
    if not isinstance(values, dict):
        raise UpstreamError("fyers", "The broker returned an unexpected quote shape.")
    return values


def _decimal(value: Any) -> Decimal | None:
    """Parse a numeric field, tolerating the broker's mixed types.

    Values arrive as int, float, or string depending on the field. ``None`` is
    returned rather than a default, so a missing figure stays visibly missing.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
