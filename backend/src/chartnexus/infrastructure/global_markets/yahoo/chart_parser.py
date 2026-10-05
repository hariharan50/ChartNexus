"""Yahoo chart payloads to canonical global quotes.

Pure functions over a parsed JSON body. No HTTP, no cache, no clock - so every
shape question is answered in one place and pinned by a test against a real
captured payload.

Shape of a response::

    {"chart": {"result": [{"meta": {...},
                           "timestamp": [...],
                           "indicators": {"quote": [{"close": [...], ...}]}}],
               "error": null}}

Three things about this payload are load-bearing and none of them are obvious:

**``chartPreviousClose`` is not yesterday's close.** It is the close before the
*requested range*, so the same symbol returns 7,551.81 for a 5-day window and
7,764.70 for a 2-day one. Reading it as "previous close" would make the board
disagree with itself whenever the range changed. The previous close is instead
derived from the authoritative ``fulldayChange``, which is the figure the
provider itself publishes and the one that matches every reference board.

**The series contains nulls.** Holidays and partial sessions arrive as ``null``
entries aligned with the timestamps, so every series read filters them - a
sparkline that plots ``None`` as zero draws a cliff to the axis that never
happened.

**A 200 is not a success.** An unknown symbol returns HTTP 200 with
``chart.error`` populated and ``result: null``, so the status code is never
trusted on its own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from chartnexus.contexts.global_markets.domain.quotes import (
    DataSource,
    GlobalQuote,
    Provenance,
)

#: A -100% move would make the recovery divisor zero. Not reachable for an
#: index, but the guard is free and a ZeroDivisionError here would take the
#: whole board down.
_TOTAL_LOSS_PERCENT = Decimal("-100")


class UnknownSymbolError(Exception):
    """The provider has no such instrument. Not a transport fault."""


def to_quote(payload: dict[str, Any], *, key: str, fetched_at: datetime) -> GlobalQuote:
    """One quote from one chart response.

    Raises :class:`UnknownSymbolError` when the provider answered but has
    nothing for this symbol, so a caller can drop the row and keep the other
    thirteen rather than failing the whole board.
    """
    meta = _meta(payload)

    price = _decimal(meta.get("regularMarketPrice"))
    if price is None:
        raise UnknownSymbolError(f"No price for {key}.")

    change = _decimal(meta.get("fulldayChange"))
    change_percent = _decimal(
        meta.get("fulldayChangePercent", meta.get("regularMarketChangePercent"))
    )

    # Derived, never read off `chartPreviousClose` - see the module docstring.
    previous_close = price - change if change is not None else None
    if change is None and change_percent is not None and change_percent != _TOTAL_LOSS_PERCENT:
        # Percent without an absolute: recover the base from the ratio rather
        # than leaving the board's previous-close column empty.
        divisor = Decimal(1) + change_percent / Decimal(100)
        if divisor != 0:
            previous_close = (price / divisor).quantize(Decimal("0.01"))
            change = price - previous_close

    return GlobalQuote(
        key=key,
        price=price,
        change=change,
        change_percent=change_percent,
        previous_close=previous_close,
        day_open=_decimal(meta.get("regularMarketOpen")),
        day_high=_decimal(meta.get("regularMarketDayHigh")),
        day_low=_decimal(meta.get("regularMarketDayLow")),
        spark=_spark(payload),
        session=_session(meta),
        provenance=Provenance(source=DataSource.LIVE, fetched_at=fetched_at),
    )


def _meta(payload: dict[str, Any]) -> dict[str, Any]:
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise UnknownSymbolError("The provider returned an unexpected envelope.")
    if chart.get("error"):
        raise UnknownSymbolError(str(chart["error"]))

    results = chart.get("result")
    if not isinstance(results, list) or not results:
        raise UnknownSymbolError("The provider returned no result.")

    meta = results[0].get("meta") if isinstance(results[0], dict) else None
    if not isinstance(meta, dict):
        raise UnknownSymbolError("The provider returned no metadata.")
    return meta


def _spark(payload: dict[str, Any]) -> tuple[Decimal, ...]:
    """Closing prints, oldest first, nulls dropped."""
    try:
        quote = payload["chart"]["result"][0]["indicators"]["quote"][0]
        closes = quote["close"]
    except (KeyError, IndexError, TypeError):
        return ()
    if not isinstance(closes, list):
        return ()

    values = [parsed for raw in closes if (parsed := _decimal(raw)) is not None]
    return tuple(values)


def _session(meta: dict[str, Any]) -> datetime | None:
    """The instant of the last print, as an aware UTC datetime.

    The timeline needs this to date a band: a New York quote read at 06:00 IST
    belongs to *yesterday's* session there, and dating it "today" would draw
    the band a full day into the future.
    """
    stamp = meta.get("regularMarketTime")
    if not isinstance(stamp, int | float) or isinstance(stamp, bool):
        return None
    try:
        return datetime.fromtimestamp(float(stamp), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _decimal(value: Any) -> Decimal | None:
    """Parse a numeric field, tolerating the provider's mixed types.

    ``None`` rather than a default, so a missing figure stays visibly missing.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
