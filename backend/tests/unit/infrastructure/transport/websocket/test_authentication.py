"""The websocket handshake.

Single-use enforcement is the point of this module, so the replay test is the
one that matters: a ticket recovered from a proxy log or a browser history must
already be spent.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from chartnexus.bootstrap.settings import AuthSettings, SecuritySettings
from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.infrastructure.security.websocket_tickets import (
    JwtWebsocketTicketIssuer,
    TicketExpiredError,
    TicketInvalidError,
)
from chartnexus.infrastructure.transport.websocket import protocol
from chartnexus.infrastructure.transport.websocket.authentication import (
    HandshakeAuthenticator,
    TicketAlreadyUsedError,
    close_code_for,
    error_code_for,
)
from chartnexus.shared_kernel.types.identifiers import SessionId, TenantId, UserId

USER = UserId(uuid.uuid4())
TENANT = TenantId(uuid.uuid4())
SESSION = SessionId(uuid.uuid4())
SECRET = "test-only-secret-key-of-sufficient-length-for-hs256"


class FakeRedisCommands:
    """Just enough Redis for the burn: ``SET`` with ``NX`` and ``EX``."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.expiries: dict[str, int] = {}
        self.fail = False

    # Named for the redis-py method it stands in for.
    async def set(
        self,
        key: str,
        value: bytes,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> Any:
        if self.fail:
            raise ConnectionError("redis is unreachable")
        if nx and key in self.store:
            return None
        self.store[key] = value
        if ex is not None:
            self.expiries[key] = ex
        return True


def _redis() -> tuple[RedisClient, FakeRedisCommands]:
    commands = FakeRedisCommands()
    client = RedisClient(client=commands, pool=None, key_prefix="cn")  # type: ignore[arg-type]
    return client, commands


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
def issuer() -> JwtWebsocketTicketIssuer:
    return JwtWebsocketTicketIssuer(AuthSettings(), SecuritySettings(secret_key=SECRET))


def _ticket(issuer: JwtWebsocketTicketIssuer, *, now: datetime | None = None) -> str:
    return issuer.issue(user_id=USER, tenant_id=TENANT, session_id=SESSION, now=now or _now()).value


class TestAcceptance:
    async def test_accepts_a_fresh_ticket(self, issuer: JwtWebsocketTicketIssuer) -> None:
        redis, _ = _redis()
        authenticator = HandshakeAuthenticator(tickets=issuer, redis=redis)

        connection = await authenticator.authenticate(_ticket(issuer), now=_now())

        assert connection.user_id == str(USER)
        assert connection.tenant_id == str(TENANT)

    async def test_burns_the_ticket_id_with_a_ttl(self, issuer: JwtWebsocketTicketIssuer) -> None:
        """The marker expires on its own, so the keyspace cannot grow unbounded."""
        redis, commands = _redis()
        authenticator = HandshakeAuthenticator(tickets=issuer, redis=redis)

        await authenticator.authenticate(_ticket(issuer), now=_now())

        assert len(commands.store) == 1
        key = next(iter(commands.store))
        assert key.startswith("cn:ws:ticket:")
        assert 0 < commands.expiries[key] <= 60


class TestReplay:
    async def test_refuses_a_second_use(self, issuer: JwtWebsocketTicketIssuer) -> None:
        redis, _ = _redis()
        authenticator = HandshakeAuthenticator(tickets=issuer, redis=redis)
        ticket = _ticket(issuer)

        await authenticator.authenticate(ticket, now=_now())

        with pytest.raises(TicketAlreadyUsedError):
            await authenticator.authenticate(ticket, now=_now())

    async def test_distinct_tickets_both_work(self, issuer: JwtWebsocketTicketIssuer) -> None:
        """Single-use must not become one-connection-per-session."""
        redis, _ = _redis()
        authenticator = HandshakeAuthenticator(tickets=issuer, redis=redis)

        await authenticator.authenticate(_ticket(issuer), now=_now())
        await authenticator.authenticate(_ticket(issuer), now=_now())

    async def test_replay_is_allowed_when_single_use_is_off(
        self, issuer: JwtWebsocketTicketIssuer
    ) -> None:
        """The documented debug escape hatch, and nothing more."""
        redis, commands = _redis()
        authenticator = HandshakeAuthenticator(tickets=issuer, redis=redis, single_use=False)
        ticket = _ticket(issuer)

        await authenticator.authenticate(ticket, now=_now())
        await authenticator.authenticate(ticket, now=_now())

        assert commands.store == {}

    async def test_a_ticket_in_its_final_moment_still_burns(
        self, issuer: JwtWebsocketTicketIssuer
    ) -> None:
        """Redis rejects a non-positive EX, and an unwritten marker is replayable."""
        redis, commands = _redis()
        authenticator = HandshakeAuthenticator(tickets=issuer, redis=redis)
        # Issued 59s ago against a 60s TTL: one second of life left.
        ticket = _ticket(issuer, now=_now() - timedelta(seconds=59))

        await authenticator.authenticate(ticket, now=_now())

        assert all(value >= 1 for value in commands.expiries.values())


class TestRefusal:
    async def test_a_missing_ticket_is_refused(self, issuer: JwtWebsocketTicketIssuer) -> None:
        redis, _ = _redis()
        authenticator = HandshakeAuthenticator(tickets=issuer, redis=redis)

        with pytest.raises(TicketInvalidError):
            await authenticator.authenticate(None, now=_now())

    async def test_an_empty_ticket_is_refused(self, issuer: JwtWebsocketTicketIssuer) -> None:
        redis, _ = _redis()
        authenticator = HandshakeAuthenticator(tickets=issuer, redis=redis)

        with pytest.raises(TicketInvalidError):
            await authenticator.authenticate("", now=_now())

    async def test_an_expired_ticket_is_never_burned(
        self, issuer: JwtWebsocketTicketIssuer
    ) -> None:
        """Verification precedes the burn, so a bad ticket costs no Redis write."""
        redis, commands = _redis()
        authenticator = HandshakeAuthenticator(tickets=issuer, redis=redis)
        stale = _ticket(issuer, now=_now() - timedelta(seconds=300))

        with pytest.raises(TicketExpiredError):
            await authenticator.authenticate(stale, now=_now())

        assert commands.store == {}

    async def test_fails_closed_when_redis_is_unreachable(
        self, issuer: JwtWebsocketTicketIssuer
    ) -> None:
        """No degrading to insecure: this process cannot deliver without Redis anyway."""
        redis, commands = _redis()
        commands.fail = True
        authenticator = HandshakeAuthenticator(tickets=issuer, redis=redis)

        with pytest.raises(ConnectionError):
            await authenticator.authenticate(_ticket(issuer), now=_now())


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("exc", "code"),
        [
            (TicketExpiredError("x"), protocol.TICKET_EXPIRED),
            (TicketAlreadyUsedError("x"), protocol.TICKET_ALREADY_USED),
            (TicketInvalidError("x"), protocol.NOT_AUTHENTICATED),
            (RuntimeError("x"), protocol.INTERNAL_ERROR),
        ],
    )
    def test_each_failure_reports_its_own_code(self, exc: Exception, code: str) -> None:
        """Three distinct refusals, because the client's correct response differs."""
        assert error_code_for(exc) == code

    @pytest.mark.parametrize(
        "exc",
        [TicketExpiredError("x"), TicketAlreadyUsedError("x"), TicketInvalidError("x")],
    )
    def test_credential_failures_close_as_policy_violations(self, exc: Exception) -> None:
        assert close_code_for(exc) == protocol.CLOSE_POLICY_VIOLATION

    def test_an_unexpected_failure_closes_as_internal_error(self) -> None:
        assert close_code_for(RuntimeError("x")) == protocol.CLOSE_INTERNAL_ERROR
