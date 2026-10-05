"""GIFT NIFTY, read from NSE International Exchange's own market watch.

The live adapter the simulator in ``simulated_source.py`` stood in for. NSE IX
serves its market-watch board as plain JSON with no key and no token::

    GET https://www.nseix.com/api/streamer-market-watch/
    {"MBP_data_Market_Watch": [{"token_number": 1215,
                                "token_data": [{"SYMBOL": "NIFTY",
                                                "EXPIRYDATE": "29-Sep-2026",
                                                "LASTPRICE": "23267.50",
                                                "CHANGE": "-48.00", ...}]}]}

Three things shape this adapter:

**The board carries several contracts.** Near month, next month, sometimes
further. Only the front month is GIFT NIFTY in the sense anyone means it, so
the nearest unexpired date wins - picked by parsing the dates rather than by
taking the first entry, because the board's order is not guaranteed.

**``LASTPRICE`` is live; ``CLOSE`` is not the previous settlement.** It was
read as one for a while, and it is not: GIFT trades two sessions a day and the
board's ``CLOSE`` is struck against the session boundary rather than the
trading day's. On 28-Sep-2026 it said 23,236.00 where the exchange's own
settlement for the same contract was 23,188.50 - a 47.5-point difference that
showed the contract down 0.43% on a morning every other screen had it down
0.25%. The previous close therefore comes from ``settlement_source``, which
reads the figure the exchange publishes end-of-day, and the board's ``CLOSE``
is kept only as the fallback for when that file cannot be read.

**It degrades to the simulator, visibly.** NSE IX is an undocumented endpoint
on a site that can change without notice; if it fails, the card falls back and
the badge says Simulated rather than quietly showing a made-up gap as fact.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final

import httpx

from chartnexus.contexts.global_markets.application.ports import GiftNiftySource
from chartnexus.contexts.global_markets.domain.markets import GIFT_KEY, IST
from chartnexus.contexts.global_markets.domain.quotes import (
    DataSource,
    GlobalQuote,
    Provenance,
)
from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.infrastructure.global_markets.nseix.settlement_source import (
    NseIxSettlements,
)
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

MARKET_WATCH_URL: Final = "https://www.nseix.com/api/streamer-market-watch/"

#: The site serves these to anything that looks like a browser.
BROWSER_HEADERS: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.nseix.com/",
}

_NAMESPACE: Final = "gift-nifty"
#: GIFT trades nearly around the clock, so there is no "closed" tier to cache
#: harder - a minute is short enough to stay current and long enough that a
#: page open all night is not hammering the exchange.
_TTL_SECONDS: Final = 60

#: The board's own date spelling. Built by hand rather than with ``strptime``'s
#: ``%b``, which is locale-dependent: a server under a non-English locale would
#: fail to parse every row.
_MONTHS: Final[dict[str, int]] = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


class NseIxGiftNiftySource(GiftNiftySource):
    """Implements ``GiftNiftySource`` against NSE IX's market watch."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        redis: RedisClient,
        *,
        fallback: GiftNiftySource,
        settlements: NseIxSettlements | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._http = http
        self._redis = redis
        self._fallback = fallback
        self._settlements = settlements
        self._timeout = httpx.Timeout(timeout_seconds)
        # Flipped by any call that had to fall back, and read by `source`
        # afterwards, so the badge describes the request being rendered.
        self._live = True

    @property
    def name(self) -> str:
        return "nseix" if self._live else "mock"

    async def get_quote(self, nifty_spot: GlobalQuote | None) -> GlobalQuote | None:
        now = datetime.now(tz=IST)
        try:
            payload = await self._payload()
            contract = front_month(payload)
            if contract is None:
                raise ValueError("No NIFTY futures row on the board.")
            self._live = True
            # Looked up for the contract actually being quoted, not for the
            # front month in the abstract: on the roll those are two different
            # contracts and two different settlements.
            settlement = await self._settlement_for(contract)
            return to_quote(contract, fetched_at=now, settlement=settlement)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            log.warning("gift_nifty_degraded", error=repr(exc))
            self._live = False
            return await self._fallback.get_quote(nifty_spot)

    async def _settlement_for(self, contract: dict[str, Any]) -> Decimal | None:
        """The contract's own previous settlement, or ``None`` to fall back.

        Never fatal. A missing settlement costs the day-change row its correct
        base; a raised exception would cost the whole card its live level, and
        the level is the figure the page exists to show.
        """
        if self._settlements is None:
            return None
        symbol = contract.get("SYMBOL")
        expiry = contract.get("EXPIRYDATE")
        if not isinstance(symbol, str) or not isinstance(expiry, str):
            return None
        return await self._settlements.previous_settlement(symbol, expiry)

    async def _payload(self) -> dict[str, Any]:
        cached = await self._cache_get()
        if cached is not None:
            return cached

        response = await self._http.get(
            MARKET_WATCH_URL, headers=BROWSER_HEADERS, timeout=self._timeout
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("NSE IX returned an unexpected body.")

        await self._cache_set(body)
        return body

    async def _cache_get(self) -> dict[str, Any] | None:
        try:
            raw = await self._redis.client.get(self._redis.key(_NAMESPACE, "market-watch"))
        except Exception as exc:
            log.warning("gift_nifty_cache_read_failed", error=repr(exc))
            return None
        if raw is None:
            return None
        try:
            parsed = json.loads(raw if isinstance(raw, str) else raw.decode())
        except Exception:
            # A corrupt entry is a miss, not a failure.
            return None
        return parsed if isinstance(parsed, dict) else None

    async def _cache_set(self, payload: dict[str, Any]) -> None:
        try:
            await self._redis.client.set(
                self._redis.key(_NAMESPACE, "market-watch"),
                json.dumps(payload),
                ex=_TTL_SECONDS,
            )
        except Exception as exc:
            log.warning("gift_nifty_cache_write_failed", error=repr(exc))


# -- parsing ------------------------------------------------------------------


def front_month(payload: dict[str, Any]) -> dict[str, Any] | None:
    """The nearest-dated NIFTY index future on the board.

    Chosen by parsing the expiry dates rather than by taking the first entry:
    the board's order is not documented and has no reason to be stable, and
    silently quoting the October contract as "GIFT NIFTY" would put the implied
    open out by the whole calendar spread.
    """
    best: tuple[tuple[int, int, int], dict[str, Any]] | None = None

    for group in payload.get("MBP_data_Market_Watch") or []:
        if not isinstance(group, dict):
            continue
        for row in group.get("token_data") or []:
            if not isinstance(row, dict) or row.get("SYMBOL") != "NIFTY":
                continue
            if row.get("INSTRUMENTTYPE") != "FUTIDX":
                continue
            expiry = _expiry_key(row.get("EXPIRYDATE"))
            if expiry is None:
                continue
            if best is None or expiry < best[0]:
                best = (expiry, row)

    return None if best is None else best[1]


def to_quote(
    row: dict[str, Any], *, fetched_at: datetime, settlement: Decimal | None = None
) -> GlobalQuote:
    """One board row as a canonical quote.

    ``LASTPRICE`` is live and is used as-is. The *previous close* comes from
    ``settlement`` when the exchange's end-of-day file could be read, and the
    change is then recomputed from it rather than copied from the board -
    ``CHANGE`` and ``PERCHANGE`` are struck against the board's own ``CLOSE``,
    so keeping them beside a different base would print a change that does not
    reconcile with the two levels next to it.
    """
    price = _decimal(row.get("LASTPRICE"))
    if price is None:
        raise ValueError("The GIFT board row carries no last price.")

    # A non-positive settlement is no settlement: it would divide by zero on
    # the percentage and, worse, print a previous close of 0.00 as fact.
    base = settlement if settlement is not None and settlement > 0 else None
    previous_close: Decimal | None
    change: Decimal | None
    change_percent: Decimal | None
    if base is not None:
        previous_close = base
        change = (price - base).quantize(Decimal("0.01"))
        change_percent = (change / base * Decimal(100)).quantize(Decimal("0.01"))
    else:
        previous_close = _decimal(row.get("CLOSE"))
        change = _decimal(row.get("CHANGE"))
        change_percent = _decimal(row.get("PERCHANGE"))

    return GlobalQuote(
        key=GIFT_KEY,
        price=price,
        change=change,
        change_percent=change_percent,
        previous_close=previous_close,
        day_open=_decimal(row.get("OPEN")),
        day_high=_decimal(row.get("HIGH")),
        day_low=_decimal(row.get("LOW")),
        spark=(),
        session=fetched_at,
        provenance=Provenance(source=DataSource.LIVE, fetched_at=fetched_at),
    )


def _expiry_key(value: Any) -> tuple[int, int, int] | None:
    """``"29-Sep-2026"`` as a sortable ``(year, month, day)``."""
    if not isinstance(value, str):
        return None
    parts = value.split("-")
    expected_parts = 3
    if len(parts) != expected_parts:
        return None
    day, month, year = parts
    if month not in _MONTHS:
        return None
    try:
        return int(year), _MONTHS[month], int(day)
    except ValueError:
        return None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
