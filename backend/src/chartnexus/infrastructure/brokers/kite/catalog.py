"""The Kite instrument catalog at runtime: daily sync, and cached lookups.

The catalog changes once a day, but a busy option-chain page asks for the same
strikes every second. Lookups are therefore cached in-process for a few
minutes, and the cache is dropped whenever this process completes a sync.
Another process's sync is picked up when its cache entries expire — at worst a
few minutes of the previous day's contract list, which is the same list until
an expiry rolls off at 15:30.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, date, datetime
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

from chartnexus.infrastructure.brokers.kite.instruments import (
    KiteInstrument,
    derivative_exchange,
    parse_dump,
    spot_key,
    validate,
)
from chartnexus.infrastructure.brokers.kite.rest_client import KiteRestClient
from chartnexus.infrastructure.catalog import registry
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.persistence.postgresql.repositories.integration.kite_instrument_repository import (
    SqlAlchemyKiteInstrumentRepository,
)

log = get_logger(__name__)

_TTL_SECONDS = 300.0
#: Contracts expire on the exchange's calendar, so "unexpired" means IST today.
_IST = ZoneInfo("Asia/Kolkata")
_T = TypeVar("_T")

#: (method, args) -> (expires_at_monotonic, value). Process-wide on purpose:
#: providers are rebuilt per request, so an instance cache would never be hit.
_CACHE: dict[tuple[Any, ...], tuple[float, Any]] = {}


def clear_cache() -> None:
    _CACHE.clear()


class KiteCatalogNotLoadedError(LookupError):
    """No Kite instrument catalog has been synced yet."""


class KiteInstrumentIndex:
    """Cached, read-only lookups over ``kite_instruments``.

    ``database`` is the process's ``Database``; each lookup opens its own short
    read session, so this works the same from a request, a sweep, or the
    ticker — none of which share a session.
    """

    def __init__(self, database: Any, *, today: Callable[[], date] | None = None) -> None:
        self._database = database
        self._today = today or (lambda: datetime.now(_IST).date())

    async def spot(self, symbol: str, listing_exchange: str) -> KiteInstrument | None:
        exchange, tradingsymbol = spot_key(symbol, listing_exchange)
        return await self._cached(
            ("spot", exchange, tradingsymbol),
            lambda repo: repo.by_symbol(exchange, tradingsymbol),
        )

    async def spot_token(self, symbol: str) -> int | None:
        """The spot's ``instrument_token``, with the listing exchange from the catalog.

        For the ticker and the ATR history call, which know only the canonical
        symbol. ``None`` when the dump has no such row (not synced yet, or an
        instrument Zerodha doesn't list).
        """
        found = registry.current().find(symbol.upper())
        listing = found.exchange if found is not None else "NSE"
        instrument = await self.spot(symbol, listing)
        return instrument.instrument_token if instrument is not None else None

    async def futures(self, futures_root: str, listing_exchange: str) -> list[KiteInstrument]:
        """Listed futures on an underlying, nearest expiry first."""
        exchange = derivative_exchange(listing_exchange)
        today = self._today()
        return await self._cached(
            ("futures", futures_root.upper(), exchange, today),
            lambda repo: repo.futures(futures_root.upper(), exchange, today=today),
        )

    async def option_expiries(self, futures_root: str, listing_exchange: str) -> list[date]:
        exchange = derivative_exchange(listing_exchange)
        today = self._today()
        return await self._cached(
            ("expiries", futures_root.upper(), exchange, today),
            lambda repo: repo.option_expiries(futures_root.upper(), exchange, today=today),
        )

    async def options(
        self, futures_root: str, listing_exchange: str, expiry: date
    ) -> list[KiteInstrument]:
        exchange = derivative_exchange(listing_exchange)
        return await self._cached(
            ("options", futures_root.upper(), exchange, expiry),
            lambda repo: repo.options(futures_root.upper(), exchange, expiry),
        )

    async def _cached(
        self,
        key: tuple[Any, ...],
        load: Callable[[SqlAlchemyKiteInstrumentRepository], Awaitable[_T]],
    ) -> _T:
        hit = _CACHE.get(key)
        now = time.monotonic()
        if hit is not None and hit[0] > now:
            value: _T = hit[1]
            return value
        async with self._database.read_session() as session:
            loaded = await load(SqlAlchemyKiteInstrumentRepository(session))
        # An empty answer is cached too, but briefly: right after the very first
        # sync it would otherwise hide the new catalog for five minutes.
        ttl = _TTL_SECONDS if loaded else 15.0
        _CACHE[key] = (now + ttl, loaded)
        return loaded


async def sync_instruments(
    *,
    database: Any,
    rest: KiteRestClient,
    api_key: str,
    access_token: str,
    equities: Iterable[str],
) -> int:
    """Download, validate, and atomically replace the Kite catalog.

    Raises on a bad download or a failed validation; the previous catalog is
    untouched in both cases. Returns the number of rows stored.
    """
    text = await rest.fetch_instruments_csv(api_key=api_key, access_token=access_token)
    rows = parse_dump(text, equities=equities)
    validate(rows)

    synced_at = datetime.now(UTC)
    async with database.session() as session:
        stored = await SqlAlchemyKiteInstrumentRepository(session).replace_all(
            rows, synced_at=synced_at
        )
    clear_cache()
    log.info("kite_instruments_synced", rows=stored)
    return stored
