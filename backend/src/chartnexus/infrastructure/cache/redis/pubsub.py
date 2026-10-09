"""Redis pub/sub fan-out.

The seam between the process that *produces* a market event and the process
that *delivers* it. The ingest worker publishes; the realtime worker subscribes
and pushes to browsers. Neither imports the other, and either can be restarted
without the other noticing.

Pub/sub, not a stream, on purpose. These events are invalidation signals with a
useful life measured in seconds: a subscriber that was down did not miss work it
must catch up on, it missed a prompt to refetch, and the next tick supersedes it.
Redis pub/sub is fire-and-forget with no backlog to replay, which is exactly the
delivery guarantee that matches. A durable stream would accumulate a queue of
stale prompts for an absent consumer and deliver them all at reconnect, which is
worse than nothing.

Channel names go through :meth:`RedisClient.key`, so two environments sharing one
Redis instance during development cannot cross-talk.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

# How long a blocking read waits before coming back empty. Caps how long a stop
# signal can go unnoticed; a subscriber loop is otherwise parked in Redis.
_POLL_TIMEOUT_SECONDS = 1.0


@dataclass(slots=True)
class Subscription:
    """An open Redis subscription, yielding decoded payloads.

    Construct through :meth:`RedisPubSub.subscription`, which owns the unsubscribe.
    """

    _pubsub: Any
    _channel: str

    async def events(self, *, stop: asyncio.Event) -> AsyncIterator[Mapping[str, Any]]:
        """Yield payloads until ``stop`` is set.

        A frame that is not valid JSON is logged and skipped rather than raised:
        the publisher is a separate process, and one bad message must not take
        down every connected browser. The same applies to a payload that decodes
        to something other than an object — the contract says object, and a bare
        list or string is a publisher bug, not a reason to stop delivering.
        """
        while not stop.is_set():
            raw = await self._pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=_POLL_TIMEOUT_SECONDS,
            )
            if raw is None:
                continue

            data = raw.get("data")
            if not isinstance(data, (bytes, bytearray, str)):
                continue

            try:
                decoded = json.loads(data)
            except (ValueError, TypeError) as exc:
                log.warning("pubsub_payload_undecodable", channel=self._channel, error=repr(exc))
                continue

            if not isinstance(decoded, dict):
                log.warning(
                    "pubsub_payload_not_an_object",
                    channel=self._channel,
                    received=type(decoded).__name__,
                )
                continue

            yield decoded


class RedisPubSub:
    """Publishes and subscribes on namespaced Redis channels."""

    def __init__(self, redis: RedisClient) -> None:
        self._redis = redis

    async def publish(self, channel: str, payload: Mapping[str, Any]) -> int:
        """Publish one payload. Returns how many subscribers received it.

        Zero is the normal, healthy answer when no browser is connected — it is
        not an error, and callers should not treat it as one.
        """
        return int(
            await self._redis.client.publish(
                self._redis.key(channel),
                json.dumps(payload, separators=(",", ":")),
            )
        )

    @asynccontextmanager
    async def subscription(self, channel: str) -> AsyncIterator[Subscription]:
        """Subscribe for the duration of the block, unsubscribing on the way out.

        The teardown suppresses errors deliberately: a connection that already
        died is the common reason a shutdown path gets here, and failing to
        unsubscribe from a dead socket must not mask the original exception.
        """
        namespaced = self._redis.key(channel)
        pubsub = self._redis.client.pubsub()
        await pubsub.subscribe(namespaced)
        log.info("pubsub_subscribed", channel=namespaced)
        try:
            yield Subscription(_pubsub=pubsub, _channel=namespaced)
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(namespaced)
            with contextlib.suppress(Exception):
                await pubsub.aclose()
            log.info("pubsub_unsubscribed", channel=namespaced)
