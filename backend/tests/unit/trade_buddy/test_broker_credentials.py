"""Where the watcher gets its Fyers credentials, and what it does when it cannot.

This path replaced a pair of environment variables. The reason matters for the
tests: a Fyers token expires daily, so the question is never "did we get a
token at startup" but "did we get one *this session*". Everything here is
about resolving late, failing quietly, and never holding a stale value.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest

import chartnexus.infrastructure.trade_buddy.broker_credentials as credentials_module
from chartnexus.contexts.trade_buddy.application.ports import (
    BrokerCredentials,
    BrokerCredentialsSource,
)
from chartnexus.infrastructure.trade_buddy.broker_credentials import (
    ConfiguredCredentials,
    ConnectedBrokerCredentials,
)

pytestmark = pytest.mark.unit


@dataclass
class FakeStoredCredentials:
    app_id: str


@dataclass
class FakeConnection:
    access_token: str | None = "tok"
    is_connected: bool = True
    status: str = "active"
    credentials: FakeStoredCredentials | None = None

    def __post_init__(self) -> None:
        if self.credentials is None:
            self.credentials = FakeStoredCredentials(app_id="APP123")


class FakeRepository:
    def __init__(self, connection: FakeConnection | None) -> None:
        self._connection = connection

    async def find_any_active(self, broker: Any) -> FakeConnection | None:
        return self._connection


class FakeDatabase:
    def __init__(self, connection: FakeConnection | None, *, raises: bool = False) -> None:
        self._connection = connection
        self._raises = raises

    @asynccontextmanager
    async def read_session(self):  # type: ignore[no-untyped-def]
        if self._raises:
            raise RuntimeError("pool exhausted")
        yield object()


class FakeContainer:
    def __init__(self, database: Any) -> None:
        self.database = database
        self.token_cipher = object()


def container_with(connection: FakeConnection | None, *, raises: bool = False) -> FakeContainer:
    return FakeContainer(FakeDatabase(connection, raises=raises))


@pytest.fixture
def patched_repository(monkeypatch):
    """Swap the SQLAlchemy repository for one returning a scripted connection."""

    def install(connection: FakeConnection | None) -> None:
        def factory(session: Any, cipher: Any) -> FakeRepository:
            return FakeRepository(connection)

        monkeypatch.setattr(
            "chartnexus.infrastructure.trade_buddy.broker_credentials."
            "SqlAlchemyBrokerConnectionRepository",
            factory,
        )

    return install


class TestTheJoinedForm:
    def test_it_joins_for_the_socket(self):
        # The SDK wants "APPID:TOKEN"; the REST call wants them apart. Joining
        # here rather than splitting a stored string keeps a colon inside
        # either half from making the split ambiguous.
        creds = BrokerCredentials(app_id="APP123", access_token="tok")
        assert creds.joined == "APP123:tok"

    def test_a_colon_in_the_token_survives(self):
        creds = BrokerCredentials(app_id="APP123", access_token="a:b:c")
        assert creds.joined == "APP123:a:b:c"
        assert creds.access_token == "a:b:c"


class TestConfiguredCredentials:
    async def test_both_set_resolves(self):
        source = ConfiguredCredentials("APP", "TOK")
        resolved = await source.fetch()
        assert resolved == BrokerCredentials(app_id="APP", access_token="TOK")

    @pytest.mark.parametrize(("app_id", "token"), [("", "TOK"), ("APP", ""), ("", "")])
    async def test_a_half_filled_pair_resolves_to_nothing(self, app_id, token):
        assert await ConfiguredCredentials(app_id, token).fetch() is None


class TestConnectedBroker:
    async def test_it_reads_the_connected_broker(self, patched_repository):
        patched_repository(FakeConnection())
        source = ConnectedBrokerCredentials(container_with(FakeConnection()))

        resolved = await source.fetch()

        assert resolved == BrokerCredentials(app_id="APP123", access_token="tok")

    async def test_nothing_connected_resolves_to_nothing(self, patched_repository):
        patched_repository(None)
        assert await ConnectedBrokerCredentials(container_with(None)).fetch() is None

    async def test_an_expired_connection_is_refused_not_used(self, patched_repository):
        # A row that exists but is no longer active is worth distinguishing
        # from one that never existed: only the first is fixed by reconnecting.
        patched_repository(FakeConnection(is_connected=False, status="expired"))
        assert await ConnectedBrokerCredentials(container_with(None)).fetch() is None

    async def test_a_connection_without_a_token_is_refused(self, patched_repository):
        patched_repository(FakeConnection(access_token=None))
        assert await ConnectedBrokerCredentials(container_with(None)).fetch() is None

    async def test_a_connection_without_an_app_id_is_refused(self, patched_repository):
        # The socket needs both halves; a partial reconnect can leave one.
        patched_repository(FakeConnection(credentials=FakeStoredCredentials(app_id="")))
        assert await ConnectedBrokerCredentials(container_with(None)).fetch() is None

    async def test_missing_credentials_object_is_refused(self, patched_repository):
        connection = FakeConnection()
        connection.credentials = None
        patched_repository(connection)
        assert await ConnectedBrokerCredentials(container_with(None)).fetch() is None


class TestFallbackAndFailure:
    async def test_the_env_override_is_used_when_nothing_is_connected(self, patched_repository):
        patched_repository(None)
        source = ConnectedBrokerCredentials(
            container_with(None), override=ConfiguredCredentials("ENVAPP", "ENVTOK")
        )

        resolved = await source.fetch()

        assert resolved == BrokerCredentials(app_id="ENVAPP", access_token="ENVTOK")

    async def test_the_connected_broker_wins_over_the_override(self, patched_repository):
        # The override exists for running against a *different* account; it
        # must not quietly shadow the one the user connected in the UI.
        patched_repository(FakeConnection())
        source = ConnectedBrokerCredentials(
            container_with(FakeConnection()), override=ConfiguredCredentials("ENVAPP", "ENVTOK")
        )

        resolved = await source.fetch()

        assert resolved is not None
        assert resolved.app_id == "APP123"

    async def test_a_database_failure_degrades_rather_than_raising(self, patched_repository):
        """A watch that dies because the pool hiccuped has turned a transient
        problem into a missed break."""
        patched_repository(FakeConnection())
        source = ConnectedBrokerCredentials(container_with(FakeConnection(), raises=True))

        assert await source.fetch() is None

    async def test_a_database_failure_still_falls_back_to_the_override(self, patched_repository):
        patched_repository(FakeConnection())
        source = ConnectedBrokerCredentials(
            container_with(FakeConnection(), raises=True),
            override=ConfiguredCredentials("ENVAPP", "ENVTOK"),
        )

        resolved = await source.fetch()

        assert resolved is not None
        assert resolved.app_id == "ENVAPP"

    async def test_a_container_without_a_pool_uses_the_override(self):
        class NoDatabase:
            database = None
            token_cipher = object()

        source = ConnectedBrokerCredentials(
            NoDatabase(), override=ConfiguredCredentials("ENVAPP", "ENVTOK")
        )

        resolved = await source.fetch()

        assert resolved is not None
        assert resolved.app_id == "ENVAPP"


class TestPortConformance:
    def test_both_satisfy_the_port(self):
        assert isinstance(ConfiguredCredentials("a", "b"), BrokerCredentialsSource)
        assert isinstance(ConnectedBrokerCredentials(object()), BrokerCredentialsSource)


class TestResolvedLate:
    async def test_every_fetch_re_reads_rather_than_caching(self, monkeypatch):
        """The property the daily expiry demands.

        A source that cached its first answer would hand the watcher the same
        token every morning, long after Fyers stopped accepting it.
        """
        calls = {"n": 0}

        class CountingRepository:
            def __init__(self, session: Any, cipher: Any) -> None:
                pass

            async def find_any_active(self, broker: Any) -> FakeConnection:
                calls["n"] += 1
                return FakeConnection(access_token=f"tok{calls['n']}")

        monkeypatch.setattr(
            credentials_module, "SqlAlchemyBrokerConnectionRepository", CountingRepository
        )

        source = ConnectedBrokerCredentials(container_with(FakeConnection()))
        first = await source.fetch()
        second = await source.fetch()

        assert first is not None and second is not None
        assert first.access_token == "tok1"
        assert second.access_token == "tok2"
