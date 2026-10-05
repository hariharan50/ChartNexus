"""GIFT NIFTY's previous settlement, read from NSE IX's own end-of-day files.

This module exists because of one wrong assumption in ``gift_source``, which
cost the GIA card its credibility: **the live board's ``CLOSE`` is not the
previous daily settlement.**

GIFT NIFTY trades two sessions a day — roughly 06:30-15:40 IST, then 16:35
through 02:45 the next morning — and the streamer's ``CLOSE`` (with the
``CHANGE`` and ``PERCHANGE`` derived from it) is struck against the session
boundary, not the trading day's. On 28-Sep-2026 that read 23,236.00 while the
exchange's own settlement for the same contract was 23,188.50: a 47.5-point
difference, enough to show the contract down 0.43% on a morning every other
screen in the market had it down 0.25%. A quote nobody can reconcile against
their terminal is worse than no quote, because it is believed first and
disbelieved later.

The exchange publishes the real figure, free and unauthenticated, in the same
place it publishes everything else::

    GET https://www.nseix.com/api/daily-reports/
    -> ... "FILEKEY": "G_T_Bhavcopy_FO_",
           "fileurl": ".../G_T_Bhavcopy_FO_250926.CSV", "date": "25-Sep-2026"

    GET that CSV
    CONTRACT_D,PREVIOUS_S,OPEN_PRICE,...,CLOSE_PRIC,SETTLEMENT,NET_CHANGE,...
    FUTIDXNIFTY29-SEP-2026,23105.5,23106,...,23188.5,23188.5,.35,...

Three things shape this adapter:

**The listing is asked which file is current, never the filename guessed.**
``G_T_Bhavcopy_FO_250926.CSV`` is DDMMYY, and a client that reconstructed it
from today's date would have to know NSE IX's holiday calendar to walk
backwards to the last published session. The exchange already knows; it says
so in the listing, and asking costs one small request.

**The futures bhavcopy, not the settlement-price file.** Both carry the same
number, but ``G_T_DSP_PRICE_`` is 3.4 MB because it prices every option strike,
against 40 KB for the futures file. Same answer, one eightieth of the traffic.

**It degrades to the board's own figures.** If the listing or the CSV cannot
be read, the caller keeps the streamer's ``CLOSE`` — visibly imperfect, but
the level on the card is still live and still right, which is the part that
matters most.
"""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal, InvalidOperation
from typing import Any, Final

import httpx

from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

DAILY_REPORTS_URL: Final = "https://www.nseix.com/api/daily-reports/"

#: The site serves these to anything that looks like a browser.
BROWSER_HEADERS: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": "https://www.nseix.com/",
}

#: The listing's stable identifier for the futures bhavcopy. Matched on this
#: rather than on the display name, which carries HTML markup and spacing the
#: exchange has no reason to keep stable.
BHAVCOPY_FILEKEY: Final = "G_T_Bhavcopy_FO_"

_NAMESPACE: Final = "nseix-settlement"

#: The listing changes once a day, but *when* in the day depends on when the
#: exchange publishes. Half an hour is short enough to pick the new file up
#: promptly and long enough that an all-night page costs two requests an hour.
_LISTING_TTL_SECONDS: Final = 30 * 60

#: A published bhavcopy never changes, and the cache key is its own URL, so a
#: new session's file is a new key rather than a stale hit. Held for a day.
_TABLE_TTL_SECONDS: Final = 24 * 60 * 60

# The bhavcopy is positional with a header row. Named once here so a column
# shift upstream is a one-line fix.
_COL_CONTRACT: Final = 0
_COL_CLOSE: Final = 5
_COL_SETTLEMENT: Final = 6
_MIN_COLUMNS: Final = 7

#: ``FUTIDXNIFTY29-SEP-2026`` — the trailing ``DD-MMM-YYYY``.
_EXPIRY_LENGTH: Final = 11

#: Only index futures. Stock futures would collide on nothing here, but the
#: prefix is what makes splitting the contract string unambiguous.
_FUTIDX: Final = "FUTIDX"


class NseIxSettlements:
    """The previous session's settlement price, per futures contract."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        redis: RedisClient,
        *,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._http = http
        self._redis = redis
        self._timeout = httpx.Timeout(timeout_seconds)

    async def previous_settlement(self, symbol: str, expiry: str) -> Decimal | None:
        """``("NIFTY", "29-Sep-2026")`` -> ``Decimal("23188.5")``, or ``None``.

        ``expiry`` is taken as the live board spells it; the bhavcopy spells
        the month in upper case, so both sides are folded before matching.
        """
        try:
            table = await self._table()
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            log.warning("nseix_settlement_unavailable", error=repr(exc))
            return None
        return table.get(contract_key(symbol, expiry))

    # -- the table -----------------------------------------------------------

    async def _table(self) -> dict[str, Decimal]:
        url = await self._bhavcopy_url()

        cached = await self._cache_get(url)
        if cached is not None:
            return {key: Decimal(value) for key, value in cached.items()}

        response = await self._http.get(url, headers=BROWSER_HEADERS, timeout=self._timeout)
        response.raise_for_status()
        table = parse_bhavcopy(response.text)
        if not table:
            raise ValueError("The futures bhavcopy carried no settlement prices.")

        await self._cache_set(url, table)
        return table

    async def _bhavcopy_url(self) -> str:
        cached = await self._redis_get(self._redis.key(_NAMESPACE, "bhavcopy-url"))
        if isinstance(cached, str) and cached:
            return cached

        response = await self._http.get(
            DAILY_REPORTS_URL, headers=BROWSER_HEADERS, timeout=self._timeout
        )
        response.raise_for_status()
        url = bhavcopy_url(response.json())
        if url is None:
            raise ValueError("The daily-report listing carries no futures bhavcopy.")

        await self._redis_set(
            self._redis.key(_NAMESPACE, "bhavcopy-url"), url, _LISTING_TTL_SECONDS
        )
        return url

    # -- cache ---------------------------------------------------------------

    async def _cache_get(self, url: str) -> dict[str, str] | None:
        raw = await self._redis_get(self._redis.key(_NAMESPACE, _slug(url)))
        if raw is None:
            return None
        try:
            parsed = json.loads(raw)
        except Exception:
            # A corrupt entry is a miss, not a failure.
            return None
        return parsed if isinstance(parsed, dict) else None

    async def _cache_set(self, url: str, table: dict[str, Decimal]) -> None:
        payload = json.dumps({key: str(value) for key, value in table.items()})
        await self._redis_set(self._redis.key(_NAMESPACE, _slug(url)), payload, _TABLE_TTL_SECONDS)

    async def _redis_get(self, key: str) -> str | None:
        try:
            raw = await self._redis.client.get(key)
        except Exception as exc:
            log.warning("nseix_settlement_cache_read_failed", error=repr(exc))
            return None
        if raw is None:
            return None
        return raw if isinstance(raw, str) else raw.decode()

    async def _redis_set(self, key: str, value: str, ttl: int) -> None:
        try:
            await self._redis.client.set(key, value, ex=ttl)
        except Exception as exc:
            log.warning("nseix_settlement_cache_write_failed", error=repr(exc))


# -- parsing ------------------------------------------------------------------


def bhavcopy_url(listing: Any) -> str | None:
    """The futures bhavcopy's URL, found anywhere in the daily-report listing.

    Walked rather than indexed. The listing nests by "Current Day" / "Next
    Day" and then by session, and that shape is the exchange's to change; the
    ``FILEKEY`` on each entry is the part worth depending on.
    """
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("FILEKEY") == BHAVCOPY_FILEKEY:
                url = node.get("fileurl")
                if isinstance(url, str) and url:
                    found.append(url)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(listing)
    # The listing can carry more than one; the first is the most recent
    # session, which is the one the current day trades against.
    return found[0] if found else None


def parse_bhavcopy(body: str) -> dict[str, Decimal]:
    """The futures bhavcopy as ``{"NIFTY|29-SEP-2026": Decimal(...)}``.

    ``SETTLEMENT`` is preferred over ``CLOSE_PRIC``: the two agree on any
    contract that traded, and only ``SETTLEMENT`` is populated on one that did
    not, so preferring the close would leave the far months empty for no gain.
    """
    table: dict[str, Decimal] = {}

    for row in csv.reader(io.StringIO(body)):
        if len(row) < _MIN_COLUMNS:
            continue
        parsed = _split_contract(row[_COL_CONTRACT])
        if parsed is None:
            continue
        price = _decimal(row[_COL_SETTLEMENT]) or _decimal(row[_COL_CLOSE])
        if price is None or price <= 0:
            continue
        table[parsed] = price

    return table


def contract_key(symbol: str, expiry: str) -> str:
    """The lookup key both sides of this module agree on."""
    return f"{symbol.strip().upper()}|{expiry.strip().upper()}"


def _split_contract(value: str) -> str | None:
    """``"FUTIDXNIFTY29-SEP-2026"`` -> ``"NIFTY|29-SEP-2026"``.

    Split from the right, because the symbol is the variable-length part:
    ``NIFTY``, ``NIFTYIT``, ``NIFTYFPI`` and ``NIFTYNXT50`` all share a prefix
    and would collide under any left-to-right match.
    """
    contract = value.strip().upper()
    if not contract.startswith(_FUTIDX):
        return None

    body = contract[len(_FUTIDX) :]
    if len(body) <= _EXPIRY_LENGTH:
        return None

    symbol, expiry = body[:-_EXPIRY_LENGTH], body[-_EXPIRY_LENGTH:]
    if not _looks_like_expiry(expiry) or not symbol:
        return None
    return f"{symbol}|{expiry}"


def _looks_like_expiry(value: str) -> bool:
    """``DD-MMM-YYYY``, checked by shape rather than parsed.

    ``strptime``'s ``%b`` is locale-dependent, and a server under a non-English
    locale would reject every row in the file.
    """
    parts = value.split("-")
    expected_parts = 3
    if len(parts) != expected_parts:
        return False
    day, month, year = parts
    return day.isdigit() and year.isdigit() and month.isalpha()


def _slug(url: str) -> str:
    """A cache-safe name for a file URL: its basename."""
    return url.rsplit("/", 1)[-1] or url


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return None
