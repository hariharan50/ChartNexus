"""The websocket application, and the connection lifecycle.

Lives in the entrypoints layer — not infrastructure — for the same reason
``ingest_runtime`` does: it wires a :class:`Container`, which adapters are
forbidden to import. The reusable parts (the codec, the registry, the Redis
bridge) are all in ``infrastructure/transport/websocket/``; this module is the
composition.

**One reader task and one writer task per connection.** A single loop cannot do
both: ``receive_text`` parks until the client speaks, and a client that says
nothing for an hour is normal, so a fan-out waiting behind it would never be
delivered. Splitting them means a client can be written to while silent, and
read from while the outbox is empty. Whichever task finishes first takes the
other down with it, so a half-open connection cannot leak a task.

**Why its own process.** A websocket is held for the length of a trading
session. An API worker occupied by one is an API worker serving nobody, and
uvicorn's worker count is small by design.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.settings import Settings
from chartnexus.contexts.realtime_delivery.domain.topics import Topic
from chartnexus.infrastructure.cache.redis.client import redis_check
from chartnexus.infrastructure.cache.redis.pubsub import RedisPubSub
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.transport.http.health import DependencyCheck, build_health_router
from chartnexus.infrastructure.transport.websocket import protocol
from chartnexus.infrastructure.transport.websocket.authentication import (
    HandshakeAuthenticator,
    close_code_for,
    error_code_for,
)
from chartnexus.infrastructure.transport.websocket.connection_manager import (
    Connection,
    ConnectionManager,
    ServerFullError,
)
from chartnexus.infrastructure.transport.websocket.redis_consumer import run_snapshot_consumer
from chartnexus.infrastructure.transport.websocket.subscriptions import TopicLimitExceededError
from chartnexus.shared_kernel.domain.errors import ValidationError

REALTIME_VERSION = "0.1.0"

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def create_app(settings: Settings) -> FastAPI:
    """Build the realtime ASGI application.

    Takes settings rather than reading them, so a test can drive the whole
    socket against a throwaway configuration.
    """
    connections = ConnectionManager(
        queue_size=settings.realtime.send_queue_size,
        max_connections=settings.realtime.max_connections,
        topic_limit=settings.realtime.max_topics_per_connection,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # No database pool: this process never reads Postgres. Every frame it
        # sends originates from a Redis message, and the detail behind that
        # prompt is fetched by the browser over REST. Opening a pool would hold
        # connections a worker that cannot use them.
        container = Container.create(settings, use_db_pool=False)
        app.state.container = container

        pubsub = RedisPubSub(container.redis)
        app.state.authenticator = HandshakeAuthenticator(
            tickets=container.websocket_tickets,
            redis=container.redis,
            single_use=settings.realtime.single_use_tickets,
        )

        stop = asyncio.Event()
        consumer = asyncio.create_task(
            run_snapshot_consumer(
                pubsub=pubsub,
                connections=connections,
                channel=settings.realtime.snapshot_channel,
                stop=stop,
            ),
            name="realtime-snapshot-consumer",
        )
        log.info(
            "realtime_starting",
            environment=settings.environment.value,
            channel=settings.realtime.snapshot_channel,
            max_connections=settings.realtime.max_connections,
            single_use_tickets=settings.realtime.single_use_tickets,
        )
        try:
            yield
        finally:
            stop.set()
            consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consumer
            log.info("realtime_stopping", open_connections=connections.open_connections)
            await container.aclose()

    app = FastAPI(
        title="ChartNexus Realtime",
        version=REALTIME_VERSION,
        summary="Websocket fan-out for market events",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    async def check_redis() -> None:
        await redis_check(app.state.container.redis)()

    app.include_router(
        build_health_router(
            version=REALTIME_VERSION,
            # Redis only. Postgres is not a dependency of this process, and
            # reporting it here would make the socket look unhealthy during a
            # database incident it is entirely unaffected by.
            checks=(DependencyCheck("redis", check_redis),),
        )
    )

    @app.websocket(settings.realtime.path)
    async def stream(websocket: WebSocket) -> None:
        await _serve(
            websocket,
            authenticator=websocket.app.state.authenticator,
            connections=connections,
        )

    return app


async def _serve(
    websocket: WebSocket,
    *,
    authenticator: HandshakeAuthenticator,
    connections: ConnectionManager,
) -> None:
    """One connection, from handshake to close."""
    # Accepted before the ticket is checked, deliberately. Rejecting at the
    # handshake gives a browser only an opaque failure event — no status, no
    # body — so a client could not tell "fetch a new ticket" from "sign in
    # again". Accepting lets the refusal arrive as a readable `error` frame.
    # The socket is authenticated or closed within a few lines either way, and
    # the connection is not registered until it is.
    await websocket.accept()

    try:
        authenticated = await authenticator.authenticate(
            websocket.query_params.get("ticket"),
            now=_now(),
        )
    except Exception as exc:  # mapped to a protocol code below, then closed
        await _refuse(websocket, exc)
        return

    try:
        connection = connections.register(
            user_id=authenticated.user_id,
            tenant_id=authenticated.tenant_id,
        )
    except ServerFullError as exc:
        log.warning("ws_rejected_server_full", limit=exc.limit)
        await _send(websocket, protocol.error(code=protocol.INTERNAL_ERROR, message=str(exc)))
        await _close(websocket, protocol.CLOSE_TRY_AGAIN_LATER)
        return

    try:
        await websocket.send_text(protocol.welcome(connection_id=connection.id, server_time=_now()))
        await _pump(websocket, connection)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # one bad socket must not stop the process
        log.error("ws_connection_failed", connection_id=connection.id, error=repr(exc))
    finally:
        connections.unregister(connection)
        await _close(websocket, protocol.CLOSE_INTERNAL_ERROR)


async def _pump(websocket: WebSocket, connection: Connection) -> None:
    """Run the reader and the writer until one of them ends."""
    reader = asyncio.create_task(_read_loop(websocket, connection), name="ws-read")
    writer = asyncio.create_task(_write_loop(websocket, connection), name="ws-write")
    done, pending = await asyncio.wait((reader, writer), return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    # Re-raise whatever ended the connection, so the caller can log a genuine
    # failure and stay quiet about an ordinary disconnect.
    for task in done:
        task.result()


async def _read_loop(websocket: WebSocket, connection: Connection) -> None:
    """Apply client messages to this connection's subscriptions."""
    while True:
        raw = await websocket.receive_text()
        try:
            message = protocol.decode_client_message(raw)
        except protocol.ProtocolError as exc:
            connection.enqueue(
                protocol.error(
                    code=exc.code, message=exc.message, correlation_id=exc.correlation_id
                )
            )
            continue

        if isinstance(message, protocol.Ping):
            connection.enqueue(
                protocol.pong(server_time=_now(), correlation_id=message.correlation_id)
            )
            continue

        try:
            topics = tuple(Topic.parse(raw_topic) for raw_topic in message.topics)
        except ValidationError as exc:
            connection.enqueue(
                protocol.error(
                    code=protocol.UNKNOWN_TOPIC,
                    message=exc.message,
                    correlation_id=message.correlation_id,
                )
            )
            continue

        if isinstance(message, protocol.Subscribe):
            try:
                connection.subscriptions.add(topics)
            except TopicLimitExceededError as exc:
                connection.enqueue(
                    protocol.error(
                        code=protocol.TOPIC_LIMIT_EXCEEDED,
                        message=str(exc),
                        correlation_id=message.correlation_id,
                    )
                )
                continue
        else:
            connection.subscriptions.remove(topics)

        connection.enqueue(
            protocol.ack(
                topics=connection.subscriptions.as_wire(),
                correlation_id=message.correlation_id,
            )
        )


async def _write_loop(websocket: WebSocket, connection: Connection) -> None:
    """Drain this connection's outbox to the socket."""
    while True:
        frame = await connection.outbox.get()
        await websocket.send_text(frame)


async def _refuse(websocket: WebSocket, exc: Exception) -> None:
    """Tell a client why its handshake failed, then close."""
    code = error_code_for(exc)
    if code == protocol.INTERNAL_ERROR:
        log.error("ws_handshake_failed", error=repr(exc))
        message = "The connection could not be established."
    else:
        log.info("ws_handshake_refused", code=code)
        message = str(exc)
    await _send(websocket, protocol.error(code=code, message=message))
    await _close(websocket, close_code_for(exc))


async def _send(websocket: WebSocket, frame: str) -> None:
    """Best-effort send. A client that has already gone is not an error."""
    with contextlib.suppress(Exception):
        await websocket.send_text(frame)


async def _close(websocket: WebSocket, code: int) -> None:
    """Best-effort close. Closing an already-closed socket raises; ignore it."""
    with contextlib.suppress(Exception):
        await websocket.close(code=code)
