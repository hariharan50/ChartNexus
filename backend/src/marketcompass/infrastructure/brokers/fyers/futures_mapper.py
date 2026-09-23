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
    OpenInterestReading,
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
    """A single-symbol quote response."""
    return to_futures_quote_from_values(
        _first_quote_values(payload),
        instrument=instrument,
        contract=contract,
        expiry=expiry,
        fetched_at=fetched_at,
    )


def to_futures_quote_from_values(
    values: dict[str, Any],
    *,
    instrument: InstrumentSymbol,
    contract: str,
    expiry: str,
    fetched_at: datetime,
) -> FuturesQuote:
    """One contract's values, already pulled out of the response envelope.

    Split from :func:`to_futures_quote` so a batched board response can be
    mapped row by row without re-parsing the envelope for each one.
    """
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
        # Read defensively and left as None when absent. FYERS' quote payload
        # is not documented to carry open interest on every contract, and the
        # build-up read must be able to say "no OI reported" rather than
        # silently classifying a contract as unchanged at zero.
        open_interest=open_interest_of(values),
        previous_open_interest=_optional_int(values.get("pdoi"), values.get("prev_oi")),
        previous_close=_decimal(values.get("prev_close_price") or values.get("pc")),
        day_open=_decimal(values.get("open_price") or values.get("o")),
        previous_volume=_optional_int(values.get("prev_volume"), values.get("pdv")),
        provenance=Provenance(source=DataSource.LIVE, fetched_at=fetched_at),
    )


def to_open_interest(
    payload: dict[str, Any],
    *,
    instrument: InstrumentSymbol,
    symbol: str,
    observed_at: datetime,
) -> OpenInterestReading | None:
    """A depth response to an open-interest reading.

    Returns ``None`` rather than raising: this is swept over two hundred
    contracts in the background, and one unquotable contract must not abort the
    sweep for the rest.

    ``pdoi`` is the previous day's close, which is exactly the baseline the
    build-up classification measures against — so when the broker supplies it
    there is nothing left to derive.
    """
    entries = payload.get("d")
    if not isinstance(entries, dict):
        return None

    # Keyed by the symbol we asked for; fall back to the sole entry, since the
    # endpoint only ever returns one.
    values = entries.get(symbol)
    if not isinstance(values, dict):
        values = next((v for v in entries.values() if isinstance(v, dict)), None)
    if values is None:
        return None

    open_interest = _optional_int(values.get("oi"))
    if open_interest is None:
        return None

    return OpenInterestReading(
        instrument=instrument,
        open_interest=open_interest,
        previous_open_interest=_optional_int(values.get("pdoi")),
        observed_at=observed_at,
    )


def open_interest_of(values: dict[str, Any]) -> int | None:
    """Open interest from a quote's values, or ``None`` if it carries none.

    Shared with the board so "did this quote have OI?" is answered in one
    place rather than by two copies of the same field-name guesswork.
    """
    return _optional_int(values.get("oi"), values.get("open_interest"))


def split_quote_batch(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """A multi-symbol quote response, keyed by broker symbol.

    Unlike :func:`_first_quote_values` this never raises: a board is assembled
    from whatever came back, and an entry the broker could not price simply
    does not appear. Failing the whole batch because one contract is
    unquotable would lose the other forty-nine.
    """
    entries = payload.get("d")
    if not isinstance(entries, list):
        return {}

    quotes: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        values = entry.get("v")
        if not isinstance(values, dict):
            continue
        # FYERS echoes the requested symbol as ``n``; some responses only carry
        # it inside the value object.
        symbol = entry.get("n") or entry.get("symbol") or values.get("symbol")
        if isinstance(symbol, str) and symbol:
            quotes[symbol.strip()] = values
    return quotes


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


def _optional_int(*candidates: Any) -> int | None:
    """The first candidate that parses, or ``None`` if none do.

    Distinct from :func:`_int`, which floors a missing value to zero. That is
    right for volume — no trades really is zero — but wrong for open interest,
    where "the broker did not report it" and "nobody holds a position" would
    otherwise be indistinguishable, and the second one would be read as a
    contract whose entire book just closed.
    """
    for value in candidates:
        if value is None or isinstance(value, bool):
            continue
        try:
            return int(Decimal(str(value)))
        except (InvalidOperation, ValueError, TypeError):
            continue
    return None


def _int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return 0
