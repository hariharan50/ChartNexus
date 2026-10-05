"""FYERS history payloads to canonical candle series.

Shape of a history response::

    {"s": "ok", "candles": [[1754457300, 24601.2, 24640.0, 24590.1, 24633.4, 0], ...]}

Each row is ``[epoch_seconds, open, high, low, close, volume]``, oldest first.
The epoch is in exchange local time on FYERS' side but delivered as a real UTC
epoch, so it converts directly.

Index history carries a zero volume — indices have no turnover of their own.
That is passed through rather than hidden: a volume pane that draws nothing is
truthful, whereas a synthesised figure beside live prices is not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import (
    Candle,
    CandleInterval,
    CandleSeries,
    DataSource,
    Provenance,
)
from chartnexus.shared_kernel.domain.errors import UpstreamError

# FYERS names its resolutions in minutes, with "D" for daily.
_RESOLUTIONS = {
    CandleInterval.M1: "1",
    CandleInterval.M5: "5",
    CandleInterval.M15: "15",
    CandleInterval.H1: "60",
    CandleInterval.D1: "D",
}

_ROW_LENGTH = 6


def to_resolution(interval: CandleInterval) -> str:
    return _RESOLUTIONS[interval]


def to_candle_series(
    payload: dict[str, Any],
    *,
    instrument: InstrumentSymbol,
    interval: CandleInterval,
    fetched_at: datetime,
) -> CandleSeries:
    rows = payload.get("candles")
    if not isinstance(rows, list):
        raise UpstreamError("fyers", "The broker returned a history response with no candles.")

    candles = tuple(candle for row in rows if (candle := _candle(row)) is not None)
    if not candles and rows:
        # Rows arrived and none of them parsed — that is a shape change, not an
        # empty range, and it must not look like a quiet market.
        raise UpstreamError("fyers", "The broker returned candles in an unrecognised shape.")

    return CandleSeries(
        instrument=instrument,
        interval=interval,
        candles=candles,
        provenance=Provenance(source=DataSource.LIVE, fetched_at=fetched_at),
    )


def _candle(row: Any) -> Candle | None:
    if not isinstance(row, list | tuple) or len(row) < _ROW_LENGTH:
        return None

    epoch, raw_open, raw_high, raw_low, raw_close, raw_volume = row[:_ROW_LENGTH]

    try:
        opened_at = datetime.fromtimestamp(float(epoch), tz=UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return None

    prices = [_decimal(value) for value in (raw_open, raw_high, raw_low, raw_close)]
    if any(price is None for price in prices):
        return None
    price_open, price_high, price_low, price_close = prices

    return Candle(
        opened_at=opened_at,
        open=price_open,  # type: ignore[arg-type]
        high=price_high,  # type: ignore[arg-type]
        low=price_low,  # type: ignore[arg-type]
        close=price_close,  # type: ignore[arg-type]
        volume=_int(raw_volume),
    )


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0
