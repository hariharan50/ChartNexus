"""The connection lifecycle, end to end.

Drives ``_serve`` against a fake websocket: handshake, welcome, subscribe, ack,
fan-out, refusal, close. No network, no Redis, no event loop full of sockets —
the reader/writer split and the refusal paths are logic, and this is where they
are pinned.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from chartnexus.bootstrap.settings import AuthSettings, SecuritySettings
from chartnexus.contexts.realtime_delivery.domain.topics import SNAPSHOTS
from chartnexus.entrypoints.realtime_runtime import _serve
from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.infrastructure.security.websocket_tickets import JwtWebsocketTicketIssuer
from chartnexus.infrastructure.transport.websocket import protocol
from chartnexus.infrastructure.transport.websocket.authentication import HandshakeAuthenticator
from chartnexus.infrastructure.transport.websocket.connection_manager import ConnectionManager
from chartnexus.shared_kernel.types.identifiers import SessionId, TenantId, UserId

SECRET = "test-only-secret-key-of-sufficient-length-for-hs256"
USER = UserId(uuid.uuid4())
TENANT = TenantId(uuid.uuid4())
SESSION = SessionId(uuid.uuid4())


class ClientGoneError(Exception):
    """Raised by the fake socket when the scripted client has nothing left to say."""


class FakeWebSocket:
    """A scripted client. Sends the given frames, then goes away."""

    def __init__(self, *, ticket: str | None, inbound: list[str] | None = None) -> None:
        self.query_params = {} if ticket is None else {"ticket": ticket}
        self._inbound = list(inbound or [])
        self.sent: list[str] = []
        self.accepted = False
        self.closed_with: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def receive_text(self) -> str:
        if not self._inbound:
            # Mimics a client that disconnects: ends the read loop, which in
            # turn takes the write loop down with it.
            raise ClientGoneError
        return self._inbound.pop(0)

    async def send_text(self, frame: str) -> None:
        self.sent.append(frame)

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code

    def frames(self) -> list[dict[str, Any]]:
        return [json.loads(frame) for frame in self.sent]

    def of_type(self, kind: str) -> list[dict[str, Any]]:
        return [frame for frame in self.frames() if frame["type"] == kind]


class FakeRedisCommands:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    # Named for the redis-py method it stands in for.
    async def set(self, key: str, value: bytes, *, ex: int | None = None, nx: bool = False) -> Any:
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


@pytest.fixture
def issuer() -> JwtWebsocketTicketIssuer:
    return JwtWebsocketTicketIssuer(AuthSettings(), SecuritySettings(secret_key=SECRET))


@pytest.fixture
def authenticator(issuer: JwtWebsocketTicketIssuer) -> HandshakeAuthenticator:
    redis = RedisClient(client=FakeRedisCommands(), pool=None, key_prefix="cn")  # type: ignore[arg-type]
    return HandshakeAuthenticator(tickets=issuer, redis=redis)


@pytest.fixture
def connections() -> ConnectionManager:
    return ConnectionManager(queue_size=8, max_connections=4, topic_limit=2)


def _ticket(issuer: JwtWebsocketTicketIssuer, *, now: datetime | None = None) -> str:
    return issuer.issue(
        user_id=USER,
        tenant_id=TENANT,
        session_id=SESSION,
        now=now or datetime.now(UTC),
    ).value


async def _serve_once(
    socket: FakeWebSocket,
    authenticator: HandshakeAuthenticator,
    connections: ConnectionManager,
) -> None:
    """Run one connection to completion, tolerating the scripted disconnect."""
    await _serve(socket, authenticator=authenticator, connections=connections)  # type: ignore[arg-type]


class TestHandshake:
    async def test_a_valid_ticket_gets_a_welcome(
        self,
        issuer: JwtWebsocketTicketIssuer,
        authenticator: HandshakeAuthenticator,
        connections: ConnectionManager,
    ) -> None:
        socket = FakeWebSocket(ticket=_ticket(issuer))

        await _serve_once(socket, authenticator, connections)

        (welcome,) = socket.of_type("welcome")
        assert welcome["protocol_version"] == protocol.PROTOCOL_VERSION
        assert welcome["connection_id"]

    async def test_a_missing_ticket_is_refused_readably(
        self, authenticator: HandshakeAuthenticator, connections: ConnectionManager
    ) -> None:
        """Accepting before verifying is what lets the reason reach the client."""
        socket = FakeWebSocket(ticket=None)

        await _serve_once(socket, authenticator, connections)

        assert socket.accepted
        (error,) = socket.of_type("error")
        assert error["error"]["code"] == protocol.NOT_AUTHENTICATED
        assert socket.closed_with == protocol.CLOSE_POLICY_VIOLATION

    async def test_an_expired_ticket_says_so(
        self,
        issuer: JwtWebsocketTicketIssuer,
        authenticator: HandshakeAuthenticator,
        connections: ConnectionManager,
    ) -> None:
        """Distinct from not_authenticated: the fix is a new ticket, not a login."""
        socket = FakeWebSocket(
            ticket=_ticket(issuer, now=datetime.now(UTC) - timedelta(seconds=300))
        )

        await _serve_once(socket, authenticator, connections)

        (error,) = socket.of_type("error")
        assert error["error"]["code"] == protocol.TICKET_EXPIRED

    async def test_a_replayed_ticket_says_so(
        self,
        issuer: JwtWebsocketTicketIssuer,
        authenticator: HandshakeAuthenticator,
        connections: ConnectionManager,
    ) -> None:
        ticket = _ticket(issuer)
        await _serve_once(FakeWebSocket(ticket=ticket), authenticator, connections)

        second = FakeWebSocket(ticket=ticket)
        await _serve_once(second, authenticator, connections)

        (error,) = second.of_type("error")
        assert error["error"]["code"] == protocol.TICKET_ALREADY_USED

    async def test_a_refused_handshake_registers_nothing(
        self, authenticator: HandshakeAuthenticator, connections: ConnectionManager
    ) -> None:
        await _serve_once(FakeWebSocket(ticket=None), authenticator, connections)

        assert connections.open_connections == 0

    async def test_a_full_server_says_try_again_later(
        self, issuer: JwtWebsocketTicketIssuer, authenticator: HandshakeAuthenticator
    ) -> None:
        full = ConnectionManager(queue_size=4, max_connections=0, topic_limit=2)
        socket = FakeWebSocket(ticket=_ticket(issuer))

        await _serve_once(socket, authenticator, full)

        assert socket.closed_with == protocol.CLOSE_TRY_AGAIN_LATER


class TestSubscriptions:
    async def test_subscribe_is_acked_with_the_whole_set(
        self,
        issuer: JwtWebsocketTicketIssuer,
        authenticator: HandshakeAuthenticator,
        connections: ConnectionManager,
    ) -> None:
        socket = FakeWebSocket(
            ticket=_ticket(issuer),
            inbound=[
                '{"type":"subscribe","topics":["snapshots:NIFTY"],"id":"r1"}',
                '{"type":"subscribe","topics":["snapshots:BANKNIFTY"],"id":"r2"}',
            ],
        )

        await _serve_once(socket, authenticator, connections)

        acks = socket.of_type("ack")
        assert acks[0] == {"type": "ack", "topics": ["snapshots:NIFTY"], "id": "r1"}
        assert acks[1]["topics"] == ["snapshots:BANKNIFTY", "snapshots:NIFTY"]

    async def test_unsubscribe_is_acked_with_what_remains(
        self,
        issuer: JwtWebsocketTicketIssuer,
        authenticator: HandshakeAuthenticator,
        connections: ConnectionManager,
    ) -> None:
        socket = FakeWebSocket(
            ticket=_ticket(issuer),
            inbound=[
                '{"type":"subscribe","topics":["snapshots:NIFTY","snapshots:*"]}',
                '{"type":"unsubscribe","topics":["snapshots:NIFTY"]}',
            ],
        )

        await _serve_once(socket, authenticator, connections)

        assert socket.of_type("ack")[-1]["topics"] == ["snapshots:*"]

    async def test_a_bad_topic_is_an_error_not_a_disconnect(
        self,
        issuer: JwtWebsocketTicketIssuer,
        authenticator: HandshakeAuthenticator,
        connections: ConnectionManager,
    ) -> None:
        socket = FakeWebSocket(
            ticket=_ticket(issuer),
            inbound=[
                '{"type":"subscribe","topics":["snapshots:nifty"],"id":"r1"}',
                '{"type":"subscribe","topics":["snapshots:NIFTY"],"id":"r2"}',
            ],
        )

        await _serve_once(socket, authenticator, connections)

        (error,) = socket.of_type("error")
        assert error["error"]["code"] == protocol.UNKNOWN_TOPIC
        assert error["error"]["id"] == "r1"
        # The connection survived and the next subscribe worked.
        assert socket.of_type("ack")[-1]["topics"] == ["snapshots:NIFTY"]

    async def test_exceeding_the_topic_cap_is_reported(
        self,
        issuer: JwtWebsocketTicketIssuer,
        authenticator: HandshakeAuthenticator,
        connections: ConnectionManager,
    ) -> None:
        socket = FakeWebSocket(
            ticket=_ticket(issuer),
            inbound=[
                '{"type":"subscribe",'
                '"topics":["snapshots:NIFTY","snapshots:BANKNIFTY","snapshots:SENSEX"]}'
            ],
        )

        await _serve_once(socket, authenticator, connections)

        (error,) = socket.of_type("error")
        assert error["error"]["code"] == protocol.TOPIC_LIMIT_EXCEEDED
        assert socket.of_type("ack") == []

    async def test_malformed_json_is_reported_and_survived(
        self,
        issuer: JwtWebsocketTicketIssuer,
        authenticator: HandshakeAuthenticator,
        connections: ConnectionManager,
    ) -> None:
        socket = FakeWebSocket(
            ticket=_ticket(issuer),
            inbound=["not json", '{"type":"ping","id":"p1"}'],
        )

        await _serve_once(socket, authenticator, connections)

        assert socket.of_type("error")[0]["error"]["code"] == protocol.MALFORMED_FRAME
        assert socket.of_type("pong")[0]["id"] == "p1"

    async def test_ping_is_answered_with_pong(
        self,
        issuer: JwtWebsocketTicketIssuer,
        authenticator: HandshakeAuthenticator,
        connections: ConnectionManager,
    ) -> None:
        socket = FakeWebSocket(ticket=_ticket(issuer), inbound=['{"type":"ping"}'])

        await _serve_once(socket, authenticator, connections)

        assert len(socket.of_type("pong")) == 1


class TestFanOutReachesTheSocket:
    async def test_a_published_event_is_written_to_a_subscriber(
        self,
        issuer: JwtWebsocketTicketIssuer,
        authenticator: HandshakeAuthenticator,
        connections: ConnectionManager,
    ) -> None:
        """The whole path: subscribe, then an event queued by the consumer lands."""
        gate = asyncio.Event()

        class Script(FakeWebSocket):
            async def receive_text(self) -> str:
                if self._inbound:
                    return self._inbound.pop(0)
                # Subscribed and acked by now: let the test publish, then wait
                # for it to have been written before disconnecting.
                await gate.wait()
                raise ClientGoneError

        socket = Script(
            ticket=_ticket(issuer),
            inbound=['{"type":"subscribe","topics":["snapshots:NIFTY"]}'],
        )

        serving = asyncio.create_task(_serve_once(socket, authenticator, connections))

        # Wait for the subscription to be in place before fanning out.
        for _ in range(200):
            await asyncio.sleep(0)
            if socket.of_type("ack"):
                break

        result = connections.fan_out(
            kind=SNAPSHOTS, symbol="NIFTY", frame='{"type":"snapshot_committed"}'
        )
        assert result.delivered == 1

        for _ in range(200):
            await asyncio.sleep(0)
            if socket.of_type("snapshot_committed"):
                break

        gate.set()
        await serving

        assert len(socket.of_type("snapshot_committed")) == 1


class TestCleanup:
    async def test_a_disconnect_unregisters_the_connection(
        self,
        issuer: JwtWebsocketTicketIssuer,
        authenticator: HandshakeAuthenticator,
        connections: ConnectionManager,
    ) -> None:
        """A leaked registration is a leaked queue and a leaked task."""
        await _serve_once(FakeWebSocket(ticket=_ticket(issuer)), authenticator, connections)

        assert connections.open_connections == 0

    async def test_the_socket_is_closed_on_the_way_out(
        self,
        issuer: JwtWebsocketTicketIssuer,
        authenticator: HandshakeAuthenticator,
        connections: ConnectionManager,
    ) -> None:
        socket = FakeWebSocket(ticket=_ticket(issuer))

        await _serve_once(socket, authenticator, connections)

        assert socket.closed_with is not None
