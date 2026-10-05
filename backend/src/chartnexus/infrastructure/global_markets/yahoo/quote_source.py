"""World index quotes, read from Yahoo's public chart endpoint.

Implements ``GlobalQuoteSource``. Four behaviours matter here and each one is
borrowed from ``breadth/nse/flow_source.py``, which solved the same problems
against a different unofficial source.

**Cached by whether the market is still trading.** A closed index's last price
is final: re-fetching the Nikkei every minute from 12:00 IST until the Indian
open is fourteen hours of requests for a number that cannot change. Open
markets cache for a minute, closed ones for half an hour. Cached *globally*,
not per tenant - an index level is a fact about the world, not about whoever
asked.

**A partial board is a good board.** Fourteen symbols are fetched
concurrently; any that fail are simply absent from the result, and the page
renders dashes for them. Failing the whole request because Shanghai timed out
would take down thirteen working rows to report one broken one.

**Degrades visibly, never silently.** If nothing at all could be fetched the
call delegates to the simulated source and reports ``source = "mock"``, so the
badge on the page keeps telling the truth about which of the two answered.

**A 200 is not a success.** The parser validates the shape it expects; see
``chart_parser``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Final

import httpx

from chartnexus.contexts.global_markets.application.ports import GlobalQuoteSource
from chartnexus.contexts.global_markets.domain.markets import (
    IST,
    MARKETS,
    GlobalMarket,
    session_window,
)
from chartnexus.contexts.global_markets.domain.quotes import (
    DataSource,
    GlobalQuote,
    QuoteSet,
)
from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.infrastructure.global_markets.yahoo.chart_parser import (
    UnknownSymbolError,
    to_quote,
)
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

HOST: Final = "https://query1.finance.yahoo.com"

#: Sent on every request. The endpoint serves anything that looks like a
#: browser and rate-limits what does not.
BROWSER_HEADERS: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

_NAMESPACE: Final = "global-quotes"
_OPEN_TTL_SECONDS: Final = 60
_CLOSED_TTL_SECONDS: Final = 30 * 60

#: Five daily bars: enough for a sparkline, small enough that fourteen of them
#: is a trivial amount of traffic.
_RANGE: Final = "5d"
_INTERVAL: Final = "1d"

_BY_SYMBOL: Final[dict[str, GlobalMarket]] = {market.symbol: market for market in MARKETS}


class YahooGlobalQuoteSource(GlobalQuoteSource):
    """Implements ``GlobalQuoteSource`` against Yahoo's chart endpoint."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        redis: RedisClient,
        *,
        fallback: GlobalQuoteSource,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._http = http
        self._redis = redis
        self._fallback = fallback
        self._timeout = httpx.Timeout(timeout_seconds)

    @property
    def name(self) -> str:
        return "yahoo"

    async def get_quotes(self, symbols: Sequence[str]) -> QuoteSet:
        fetched_at = datetime.now(tz=IST)
        results = await asyncio.gather(
            *(self._one(symbol, fetched_at) for symbol in symbols),
            return_exceptions=True,
        )

        quotes: dict[str, GlobalQuote] = {}
        for symbol, result in zip(symbols, results, strict=True):
            if isinstance(result, GlobalQuote):
                quotes[result.key] = result
                continue
            if isinstance(result, BaseException):
                log.warning("global_quote_failed", symbol=symbol, error=repr(result))

        if not quotes:
            # Nothing at all came back: the endpoint is unreachable or has
            # started refusing us. Hand the whole board to the simulator and
            # say so, rather than rendering fourteen dashes.
            log.warning("global_quotes_degraded", provider=self.name)
            return await self._fallback.get_quotes(symbols)

        # A partial board is not a live board. Some symbols answered and some
        # did not, so the badge says "cached" rather than claiming a complete
        # live read the page did not actually get.
        source = DataSource.LIVE if len(quotes) == len(symbols) else DataSource.CACHED
        return QuoteSet(quotes=quotes, source=source, fetched_at=fetched_at)

    # -- one symbol ----------------------------------------------------------

    async def _one(self, symbol: str, fetched_at: datetime) -> GlobalQuote:
        market = _BY_SYMBOL.get(symbol)
        key = market.key if market else symbol

        cached = await self._cache_get(symbol)
        if cached is not None:
            return to_quote(cached, key=key, fetched_at=fetched_at)

        payload = await self._fetch(symbol)
        quote = to_quote(payload, key=key, fetched_at=fetched_at)
        await self._cache_set(symbol, payload, market, fetched_at)
        return quote

    async def _fetch(self, symbol: str) -> dict[str, Any]:
        response = await self._http.get(
            f"{HOST}/v8/finance/chart/{symbol}",
            params={"range": _RANGE, "interval": _INTERVAL},
            headers=BROWSER_HEADERS,
            timeout=self._timeout,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise UnknownSymbolError(f"{symbol}: unexpected response body.")
        return body

    # -- cache ---------------------------------------------------------------

    def _ttl(self, market: GlobalMarket | None, now: datetime) -> int:
        """A minute while the market trades, half an hour once it has shut."""
        if market is None:
            return _OPEN_TTL_SECONDS
        opens_at, closes_at = session_window(market, now.astimezone(IST).date())
        local = now.astimezone(IST)
        return _OPEN_TTL_SECONDS if opens_at <= local < closes_at else _CLOSED_TTL_SECONDS

    async def _cache_get(self, symbol: str) -> dict[str, Any] | None:
        try:
            raw = await self._redis.client.get(self._redis.key(_NAMESPACE, symbol))
        except Exception as exc:
            log.warning("global_quote_cache_read_failed", error=repr(exc))
            return None
        if raw is None:
            return None
        try:
            parsed = json.loads(raw if isinstance(raw, str) else raw.decode())
        except Exception:
            # A corrupt entry is a miss, not a failure.
            return None
        return parsed if isinstance(parsed, dict) else None

    async def _cache_set(
        self,
        symbol: str,
        payload: dict[str, Any],
        market: GlobalMarket | None,
        now: datetime,
    ) -> None:
        try:
            await self._redis.client.set(
                self._redis.key(_NAMESPACE, symbol),
                json.dumps(payload),
                ex=self._ttl(market, now),
            )
        except Exception as exc:
            log.warning("global_quote_cache_write_failed", error=repr(exc))
