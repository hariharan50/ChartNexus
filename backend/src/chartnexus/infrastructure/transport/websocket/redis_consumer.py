"""Redis to sockets.

One subscription for the whole process, not one per connection or per symbol.
Five hundred browsers watching NIFTY cost one Redis subscription and one decode;
routing to the interested connections is a string compare in
:class:`ConnectionManager`. The alternative — a subscription per connection —
multiplies Redis-side work by the number of readers to save work that is
already nearly free.

A malformed event is logged and skipped. The publisher is a different process
that deploys independently, so a field it forgot must cost one event, not every
connected browser.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from chartnexus.contexts.realtime_delivery.domain.topics import SNAPSHOTS, snapshots_for
from chartnexus.infrastructure.cache.redis.pubsub import RedisPubSub
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.transport.websocket import protocol
from chartnexus.infrastructure.transport.websocket.connection_manager import ConnectionManager
from chartnexus.shared_kernel.domain.errors import ValidationError

log = get_logger(__name__)

# Keys an event must carry to be deliverable. `spot` and `expiry` are optional
# because the provider may not quote them — the contract types them nullable.
_REQUIRED = ("symbol", "session_date", "captured_at", "source")


async def run_snapshot_consumer(
    *,
    pubsub: RedisPubSub,
    connections: ConnectionManager,
    channel: str,
    stop: asyncio.Event,
) -> None:
    """Bridge the snapshot channel to open connections until ``stop`` is set."""
    log.info("ws_consumer_starting", channel=channel)
    try:
        async with pubsub.subscription(channel) as subscription:
            async for event in subscription.events(stop=stop):
                _deliver(event, connections=connections)
    finally:
        log.info("ws_consumer_stopping", channel=channel)


def _deliver(event: Mapping[str, Any], *, connections: ConnectionManager) -> None:
    """Route one decoded event. Never raises — the loop must outlive a bad one."""
    missing = [key for key in _REQUIRED if not event.get(key)]
    if missing:
        log.warning("ws_event_incomplete", missing=missing)
        return

    symbol = str(event["symbol"])
    try:
        topic = snapshots_for(symbol)
    except ValidationError:
        # The publisher sent a symbol the topic grammar refuses — lower case, or
        # punctuation. No client could ever have subscribed to it, so there is
        # nobody to deliver to; worth a warning because it means the publisher
        # and the catalog disagree.
        log.warning("ws_event_unroutable_symbol", symbol=symbol)
        return

    frame = protocol.snapshot_committed(
        topic=str(topic),
        published_at=str(event.get("published_at") or event["captured_at"]),
        payload=protocol.SnapshotPayload(
            symbol=symbol,
            session_date=str(event["session_date"]),
            captured_at=str(event["captured_at"]),
            source=str(event["source"]),
            spot=_optional_str(event.get("spot")),
            expiry=_optional_str(event.get("expiry")),
        ),
    )

    result = connections.fan_out(kind=SNAPSHOTS, symbol=symbol, frame=frame)
    if result.is_noop:
        # Nobody is watching this symbol. Debug, not info: during market hours
        # with no browser open this would otherwise log once per symbol per tick.
        log.debug("ws_event_undelivered", symbol=symbol)
        return
    log.info(
        "ws_event_delivered",
        symbol=symbol,
        delivered=result.delivered,
        degraded=result.degraded,
    )


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)
