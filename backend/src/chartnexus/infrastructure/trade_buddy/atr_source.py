"""ATR(14) per instrument, from the broker's daily candles.

The number that makes one set of thresholds mean the same thing on NIFTY,
BANKNIFTY and SENSEX. Everything about *why* lives in
``contexts/trade_buddy/domain/bands.py``; this only fetches the input.

Three deliberate choices:

**Credentials resolved per call, not held.** They come from the broker the
user connected in the app (see ``broker_credentials.py``), and a Fyers token
expires daily — so caching one on this object would mean a watcher holding a
dead token by the next morning with nothing to say so.

**Raw payload, not ``CandleSeries``.** That type belongs to the ``market_data``
context, which ``trade_buddy`` may not import. The Fyers history rows are a
documented shape (``[epoch, open, high, low, close, volume]``, oldest first)
and the three columns ATR needs are read straight off them.

**Failure returns ``None``.** Thin history, an expired token, a provider
outage — none of them should stop the watch. The caller falls back to point
bands and reports that it has, because a silent fallback is the original bug
wearing a different hat.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.trade_buddy.application.ports import (
    BrokerCredentials,
    BrokerCredentialsSource,
)
from chartnexus.infrastructure.brokers.fyers.rest_client import FyersRestClient
from chartnexus.infrastructure.brokers.fyers.symbol_mapper import to_broker_symbol
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.shared_kernel.domain.indicators import atr as wilder_atr

log = get_logger(__name__)

#: FYERS names daily candles "D".
_DAILY = "D"

#: Calendar days of history requested. Wilder's ATR needs `period + 1` *trading*
#: days, and a calendar window loses weekends and holidays — roughly 30% — so a
#: 14-period ATR is asked for with a wide margin rather than a tight one. The
#: cost of over-asking is a slightly larger payload, once a day.
_LOOKBACK_DAYS = 90

#: Kite's interval name for daily candles.
_KITE_DAILY = "day"

#: Both brokers return ``[time, open, high, low, close, volume(, oi)]`` rows.
_ROW_LENGTH = 6
_HIGH, _LOW, _CLOSE = 2, 3, 4


class KiteHistorical(Protocol):
    """The slice of ``KiteRestClient`` this needs."""

    async def fetch_historical(
        self,
        *,
        api_key: str,
        access_token: str,
        instrument_token: int,
        interval: str,
        start: datetime,
        end: datetime,
        continuous: bool = False,
        oi: bool = False,
    ) -> list[list[Any]]: ...


class KiteDailyCandles:
    """Daily candles from Kite, addressed by the spot's instrument token."""

    def __init__(
        self,
        client: KiteHistorical,
        resolve_token: Callable[[str], Awaitable[int | None]],
    ) -> None:
        self._client = client
        self._resolve = resolve_token

    async def fetch(
        self, symbol: str, credentials: BrokerCredentials, start: datetime, end: datetime
    ) -> dict[str, Any]:
        token = await self._resolve(symbol)
        if token is None:
            raise LookupError(f"no Kite instrument for {symbol}")
        candles = await self._client.fetch_historical(
            api_key=credentials.app_id,
            access_token=credentials.access_token,
            instrument_token=token,
            interval=_KITE_DAILY,
            start=start,
            end=end,
        )
        return {"candles": candles}


class FyersAtrSource:
    """Implements the ``AtrSource`` port against the connected broker's history.

    Named for its first broker; a Kite connection is served by ``kite`` when
    one is wired (ADR 0002). Which path runs is decided per call by the
    credentials' ``broker``, because the connected broker can change while the
    watcher is running.
    """

    def __init__(
        self,
        client: FyersRestClient,
        credentials: BrokerCredentialsSource,
        *,
        kite: KiteDailyCandles | None = None,
        lookback_days: int = _LOOKBACK_DAYS,
    ) -> None:
        self._client = client
        self._credentials = credentials
        self._kite = kite
        self._lookback_days = lookback_days

    async def atr(self, symbol: str, *, period: int = 14) -> float | None:
        """Wilder's ATR over daily candles, or ``None`` if it cannot be computed."""
        credentials = await self._credentials.fetch()
        if credentials is None:
            log.warning("trade_buddy_atr_no_credentials", symbol=symbol)
            return None

        try:
            payload = await self._history(symbol, credentials)
        except Exception as exc:
            log.warning(
                "trade_buddy_atr_fetch_failed",
                symbol=symbol,
                broker=credentials.broker,
                error=repr(exc),
            )
            return None

        highs, lows, closes = _columns(payload)
        if not highs:
            log.warning("trade_buddy_atr_no_candles", symbol=symbol)
            return None

        # `wilder_atr` returns None below `period + 1` aligned bars rather than
        # fabricating a figure from a thin series — a level band scaled off a
        # made-up ATR would be worse than one that admits it is unscaled.
        value = wilder_atr(highs, lows, closes, period)
        if value is None or value <= 0:
            log.warning(
                "trade_buddy_atr_unavailable", symbol=symbol, bars=len(highs), period=period
            )
            return None

        log.info("trade_buddy_atr", symbol=symbol, atr=round(value, 2), bars=len(highs))
        return value

    async def _history(self, symbol: str, credentials: BrokerCredentials) -> Any:
        now = datetime.now(UTC)
        if credentials.broker == "kite":
            if self._kite is None:
                raise LookupError("Kite history is not wired")
            # Kite's timestamps are exchange-local; a date window is all ATR needs.
            end = now.replace(tzinfo=None)
            return await self._kite.fetch(
                symbol, credentials, end - timedelta(days=self._lookback_days), end
            )
        today = now.date()
        return await self._client.fetch_history(
            app_id=credentials.app_id,
            access_token=credentials.access_token,
            symbol=self._broker_symbol(symbol),
            resolution=_DAILY,
            range_from=(today - timedelta(days=self._lookback_days)).isoformat(),
            range_to=today.isoformat(),
        )

    def _broker_symbol(self, symbol: str) -> str:
        """Canonical name to the broker's string, via the instrument catalog.

        Not derivable by pattern — `BANKNIFTY` is quoted as `NIFTYBANK` — which
        is exactly why this goes through the catalog rather than an f-string.

        This file is infrastructure, not a bounded context, so reaching
        `market_data` for the symbol type is allowed; the context above it
        reaches this adapter only through the exempted bridge.
        """
        return to_broker_symbol(InstrumentSymbol(symbol))


def _columns(payload: Any) -> tuple[list[float], list[float], list[float]]:
    """Highs, lows and closes from a history payload, skipping malformed rows."""
    if not isinstance(payload, dict):
        return [], [], []
    rows = payload.get("candles")
    if not isinstance(rows, list):
        return [], [], []

    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < _ROW_LENGTH:
            continue
        try:
            high = float(row[_HIGH])
            low = float(row[_LOW])
            close = float(row[_CLOSE])
        except (TypeError, ValueError):
            continue
        # A bar with a non-positive price, or a high below its low, is corrupt.
        # Dropping it keeps one bad row from distorting the whole average.
        if high <= 0 or low <= 0 or close <= 0 or high < low:
            continue
        highs.append(high)
        lows.append(low)
        closes.append(close)
    return highs, lows, closes
