"""Shared quote cache with hot-set batching — the answer to Kite's 1 quote/s.

A ChartNexus page asks for several quotes a second: three index spots, a
future, an option chain. Kite allows one ``/quote`` request per second per API
key, but each request may carry 500 instruments. So instead of one request per
question, one request answers **everything that has been asked about
recently**:

1. Every lookup records its instruments in a per-key *hot set* (a Redis sorted
   set scored by last-asked time) and reads them from the cache first.
2. Whatever is missing is fetched by whichever caller wins a short Redis lock.
   That caller adds the rest of the hot set to the same request, so the next
   question about any recently-watched instrument is answered from cache.
3. Callers that lose the lock poll the cache briefly instead of sending their
   own request — the winner's response almost always covers them.

Entries live for ``quote_cache_seconds`` (1.5 s by default): long enough to
serve a page's burst from one request, short enough that a price is never
staler than the next request window.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, cast

from chartnexus.contexts.broker_connections.domain.errors import BrokerUnavailableError
from chartnexus.infrastructure.brokers.kite.rest_client import BROKER, QUOTE_BATCH_LIMIT
from chartnexus.infrastructure.cache.redis.client import RedisClient

#: How long a request lock may be held before it is presumed abandoned.
_LOCK_MS = 4_000
#: How long a caller that lost the lock waits for the winner's answer.
_WAIT_SECONDS = 1.5
_POLL_SECONDS = 0.1

# Release the lock only if we still own it; a plain DEL could release a lock a
# later caller took after ours expired.
_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""

Fetch = Callable[[list[str]], Awaitable[dict[str, Any]]]


class KiteQuoteCache:
    def __init__(
        self,
        redis: RedisClient,
        *,
        api_key: str,
        ttl_seconds: float = 1.5,
        hot_seconds: float = 10.0,
    ) -> None:
        self._redis = redis
        self._api_key = api_key
        self._ttl_ms = max(1, int(ttl_seconds * 1000))
        self._hot_seconds = hot_seconds

    async def quotes(self, keys: Sequence[str], fetch: Fetch) -> dict[str, dict[str, Any]]:
        """Quotes for ``keys`` (``EXCHANGE:SYMBOL``), from cache or one shared fetch.

        ``fetch`` performs one guarded ``/quote`` call for at most 500 keys.
        Keys the broker does not know are absent from the result.
        """
        wanted = list(dict.fromkeys(keys))
        if not wanted:
            return {}
        await self._mark_hot(wanted)

        found = await self._read(wanted)
        deadline = time.monotonic() + _WAIT_SECONDS
        while True:
            missing = [key for key in wanted if key not in found]
            if not missing:
                return found

            token = await self._try_lock()
            if token is not None:
                try:
                    fresh = await self._fetch_with_hot_set(missing, fetch)
                finally:
                    await self._unlock(token)
                found.update({key: fresh[key] for key in wanted if key in fresh})
                return found

            if time.monotonic() >= deadline:
                # The lock holder is slow or stuck. Better to degrade to the
                # last good value than to queue more requests behind it.
                raise BrokerUnavailableError(BROKER)
            await asyncio.sleep(_POLL_SECONDS)
            found.update(await self._read(missing))

    async def _fetch_with_hot_set(self, missing: list[str], fetch: Fetch) -> dict[str, Any]:
        fresh: dict[str, Any] = {}
        batches = [
            missing[i : i + QUOTE_BATCH_LIMIT] for i in range(0, len(missing), QUOTE_BATCH_LIMIT)
        ]
        # Fill the last batch's spare room with recently-watched instruments,
        # so they ride along on a request that is being made anyway.
        room = QUOTE_BATCH_LIMIT - len(batches[-1])
        if room > 0:
            requested = set(missing)
            extras = [key for key in await self._hot_set() if key not in requested][:room]
            batches[-1] = batches[-1] + extras

        for batch in batches:
            fresh.update(await fetch(batch))
        await self._write(fresh)
        return fresh

    # -- redis ------------------------------------------------------------------

    def _quote_key(self, instrument: str) -> str:
        return self._redis.key("kite", "quote", self._api_key, instrument)

    def _hot_key(self) -> str:
        return self._redis.key("kite", "hot", self._api_key)

    def _lock_key(self) -> str:
        return self._redis.key("kite", "quote-lock", self._api_key)

    async def _read(self, keys: Sequence[str]) -> dict[str, dict[str, Any]]:
        raw = await self._redis.client.mget([self._quote_key(key) for key in keys])
        found: dict[str, dict[str, Any]] = {}
        for key, value in zip(keys, raw, strict=True):
            if value is None:
                continue
            try:
                found[key] = json.loads(value)
            except (TypeError, ValueError):
                continue
        return found

    async def _write(self, quotes: dict[str, Any]) -> None:
        if not quotes:
            return
        pipeline = self._redis.client.pipeline()
        for key, quote in quotes.items():
            pipeline.set(self._quote_key(key), json.dumps(quote), px=self._ttl_ms)
        await pipeline.execute()

    async def _mark_hot(self, keys: Sequence[str]) -> None:
        now = time.time()
        pipeline = self._redis.client.pipeline()
        pipeline.zadd(self._hot_key(), dict.fromkeys(keys, now))
        pipeline.zremrangebyscore(self._hot_key(), 0, now - self._hot_seconds)
        pipeline.expire(self._hot_key(), int(self._hot_seconds) + 5)
        await pipeline.execute()

    async def _hot_set(self) -> list[str]:
        members = await self._redis.client.zrevrange(self._hot_key(), 0, QUOTE_BATCH_LIMIT - 1)
        return [m.decode() if isinstance(m, bytes) else str(m) for m in members]

    async def _try_lock(self) -> str | None:
        token = secrets.token_hex(8)
        acquired = await self._redis.client.set(self._lock_key(), token, nx=True, px=_LOCK_MS)
        return token if acquired else None

    async def _unlock(self, token: str) -> None:
        # redis-py types eval as sync-or-async; on the asyncio client it awaits.
        await cast("Awaitable[Any]", self._redis.client.eval(_RELEASE, 1, self._lock_key(), token))
