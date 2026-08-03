"""FYERS quote payloads to canonical futures quotes.

The futures quote arrives through the same ``/quotes`` endpoint as the spot, so
the payload shape matches :mod:`quote_mapper`. Beyond last price it also carries
the day's traded volume and high/low, which the futures card renders.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    DataSource,
    FuturesQuote,
    Provenance,
)
from marketcompass.shared_kernel.domain.errors import UpstreamError


def to_futures_quote(
    payload: dict[str, Any],
    *,
    instrument: InstrumentSymbol,
    contract: str,
    expiry: str,
    fetched_at: datetime,
) -> FuturesQuote:
    values = _first_quote_values(payload)

    price = _decimal(values.get("lp"))
    if price is None:
        # A quote with no last price is not a quote — raising lets the caller
        # degrade to cached/mock instead of rendering a zero future.
        raise UpstreamError("fyers", "The broker returned a futures quote with no price.")

    return FuturesQuote(
        instrument=instrument,
        contract=contract,
        expiry=expiry,
        price=price,
        change=_decimal(values.get("ch")),
        change_percent=_decimal(values.get("chp")),
        volume=_int(values.get("volume") or values.get("vol")),
        day_high=_decimal(values.get("high_price") or values.get("h")),
        day_low=_decimal(values.get("low_price") or values.get("l")),
        provenance=Provenance(source=DataSource.LIVE, fetched_at=fetched_at),
    )


def _first_quote_values(payload: dict[str, Any]) -> dict[str, Any]:
    entries = payload.get("d")
    if not isinstance(entries, list) or not entries:
        raise UpstreamError("fyers", "The broker returned no futures quote data.")

    first = entries[0]
    values = first.get("v") if isinstance(first, dict) else None
    if not isinstance(values, dict):
        raise UpstreamError("fyers", "The broker returned an unexpected futures quote shape.")
    return values


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return 0
