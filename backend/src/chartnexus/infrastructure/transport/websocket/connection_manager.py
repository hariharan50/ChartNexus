"""The connection registry and the fan-out.

Holds every open connection in this process and pushes an event to the ones
that asked for it. Deliberately knows nothing about ``WebSocket``: it moves
encoded frames into per-connection queues, and the endpoint drains them. That
keeps the routing — the part with the rules worth testing — testable without a
socket, a client or an event loop full of network.

**One encode per event, not one per recipient.** The contract says a frame
always names the concrete ``snapshots:<SYMBOL>`` topic, even for a client that
subscribed with ``snapshots:*``. That was chosen partly so wildcard and exact
subscribers receive byte-identical frames: the fan-out serialises once and hands
the same string to five hundred queues.

**Backpressure drops, it does not block or disconnect.** Every frame is an
invalidation prompt, so the newest is strictly more useful than the oldest, and
the next one restores a lagging client to current. A full queue therefore loses
its oldest entry. Blocking would let one slow consumer stall delivery to
everyone; disconnecting would punish a client for a hiccup it would have
recovered from in a second.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field

from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.transport.websocket.subscriptions import SubscriptionSet

log = get_logger(__name__)


class ServerFullError(Exception):
    """This process already holds its configured maximum of connections."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"This server is at its limit of {limit} connections.")
        self.limit = limit


@dataclass(slots=True)
class Connection:
    """One open websocket, from the router's point of view."""

    id: str
    user_id: str
    tenant_id: str
    subscriptions: SubscriptionSet
    outbox: asyncio.Queue[str]
    #: Frames discarded because this connection could not keep up. Logged at
    #: disconnect: a non-zero count is the signal that a client is too slow or
    #: the queue is sized too small, and it is invisible otherwise.
    dropped: int = field(default=0)

    def enqueue(self, frame: str) -> bool:
        """Queue a frame. ``False`` means an older one was dropped to fit."""
        try:
            self.outbox.put_nowait(frame)
        except asyncio.QueueFull:
            # Discard the oldest, then retry. The queue has a single consumer
            # (this connection's send loop), so nothing else can take the slot
            # between these two calls.
            with contextlib.suppress(asyncio.QueueEmpty):
                # pragma: no cover - only if the consumer raced us to the slot
                self.outbox.get_nowait()
            self.dropped += 1
            try:
                self.outbox.put_nowait(frame)
            except asyncio.QueueFull:  # pragma: no cover - consumer raced us
                return False
            return False
        return True


@dataclass(frozen=True, slots=True)
class FanOutResult:
    """What one published event actually did."""

    delivered: int
    degraded: int

    @property
    def is_noop(self) -> bool:
        """Nobody was listening. Normal and healthy, not an error."""
        return self.delivered == 0


class ConnectionManager:
    """Owns the open connections of one realtime process."""

    def __init__(self, *, queue_size: int, max_connections: int, topic_limit: int) -> None:
        self._queue_size = queue_size
        self._max_connections = max_connections
        self._topic_limit = topic_limit
        self._connections: dict[str, Connection] = {}

    def register(self, *, user_id: str, tenant_id: str) -> Connection:
        """Admit a connection, or raise :class:`ServerFullError`.

        The cap is checked here rather than at the socket, so it is enforced in
        one place no matter how many endpoints eventually accept connections.
        """
        if len(self._connections) >= self._max_connections:
            raise ServerFullError(self._max_connections)

        connection = Connection(
            id=uuid.uuid4().hex,
            user_id=user_id,
            tenant_id=tenant_id,
            subscriptions=SubscriptionSet(limit=self._topic_limit),
            outbox=asyncio.Queue(maxsize=self._queue_size),
        )
        self._connections[connection.id] = connection
        log.info(
            "ws_connection_registered",
            connection_id=connection.id,
            user_id=user_id,
            open_connections=len(self._connections),
        )
        return connection

    def unregister(self, connection: Connection) -> None:
        """Forget a connection. Safe to call twice — a socket can fail on both
        the read and the write path, and both unwind through here."""
        if self._connections.pop(connection.id, None) is None:
            return
        log.info(
            "ws_connection_unregistered",
            connection_id=connection.id,
            user_id=connection.user_id,
            dropped_frames=connection.dropped,
            open_connections=len(self._connections),
        )

    def fan_out(self, *, kind: str, symbol: str, frame: str) -> FanOutResult:
        """Queue ``frame`` on every connection subscribed to this event.

        Iterates a snapshot of the registry: a connection closing mid-fan-out
        would otherwise mutate the dict under the loop, and a frame queued to a
        connection that is already unwinding is harmless — its send loop is gone
        and the queue is discarded with it.
        """
        delivered = 0
        degraded = 0
        for connection in tuple(self._connections.values()):
            if connection.subscriptions.matching(kind, symbol) is None:
                continue
            delivered += 1
            if not connection.enqueue(frame):
                degraded += 1
        return FanOutResult(delivered=delivered, degraded=degraded)

    @property
    def open_connections(self) -> int:
        return len(self._connections)
