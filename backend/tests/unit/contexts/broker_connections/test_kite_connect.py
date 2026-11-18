"""Two brokers, one active: the rules ADR 0002 adds to connecting.

* credentials are validated by the broker they belong to;
* a Kite token's known 06:00 IST expiry is honoured without a network call;
* connecting one broker disconnects the other (keys kept, remote session ended);
* logging in as an account other than the saved Client ID stores nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from chartnexus.contexts.broker_connections.application.connect import (
    CompleteConnect,
    CompleteConnectCommand,
    ConnectPolicy,
    SaveCredentials,
    SaveCredentialsCommand,
)
from chartnexus.contexts.broker_connections.application.ports import (
    BrokerTokens,
    PendingConnection,
)
from chartnexus.contexts.broker_connections.domain.connection import BrokerConnection
from chartnexus.contexts.broker_connections.domain.errors import (
    BrokerAccountMismatchError,
    ConnectionExpiredError,
)
from chartnexus.contexts.broker_connections.domain.value_objects import (
    BrokerCredentials,
    BrokerName,
    BrokerProfile,
    ConnectionStatus,
    parse_client_id,
)
from chartnexus.shared_kernel.domain.errors import ValidationError
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId, new_id

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 3, 3, 40, tzinfo=UTC)  # 09:10 IST
KITE_KEY = "abc123xyz789"
KITE_SECRET = "s3cretvalue0123456789"
FYERS = BrokerCredentials("ABCDE123XY-100", "app-secret-value")
KITE = BrokerCredentials.parse(KITE_KEY, KITE_SECRET, BrokerName.KITE)


# --- credentials per broker ------------------------------------------------


class TestKiteCredentials:
    def test_a_kite_key_is_lower_cased(self) -> None:
        assert BrokerCredentials.parse(" ABC123XYZ789 ", KITE_SECRET, BrokerName.KITE).app_id == (
            KITE_KEY
        )

    def test_a_fyers_app_id_is_not_a_kite_key(self) -> None:
        with pytest.raises(ValidationError):
            BrokerCredentials.parse("ABCDE123XY-100", KITE_SECRET, BrokerName.KITE)

    def test_a_kite_key_is_not_a_fyers_app_id(self) -> None:
        with pytest.raises(ValidationError):
            BrokerCredentials.parse(KITE_KEY, KITE_SECRET, BrokerName.FYERS)

    @pytest.mark.parametrize("secret", ["short", "has-dashes-0123456789", "x" * 65])
    def test_a_malformed_kite_secret_is_refused(self, secret: str) -> None:
        with pytest.raises(ValidationError) as raised:
            BrokerCredentials.parse(KITE_KEY, secret, BrokerName.KITE)
        assert raised.value.details["field"] == "secret"

    def test_a_kite_key_is_masked_at_both_ends(self) -> None:
        assert KITE.masked_app_id == "abc1******89"

    def test_the_secret_is_never_in_the_repr(self) -> None:
        assert KITE_SECRET not in repr(KITE)
        assert "kite" in repr(KITE)


class TestClientId:
    def test_empty_means_unchecked(self) -> None:
        assert parse_client_id("") is None
        assert parse_client_id(None) is None

    def test_it_is_upper_cased(self) -> None:
        assert parse_client_id(" ab1234 ") == "AB1234"

    @pytest.mark.parametrize("value", ["1AB234", "AB", "AB-1234", "ABCDEFGHIJKL"])
    def test_a_malformed_id_is_refused(self, value: str) -> None:
        with pytest.raises(ValidationError):
            parse_client_id(value)


# --- expiry ------------------------------------------------------------------


def _active_kite(expires_at: datetime | None) -> BrokerConnection:
    connection = BrokerConnection.start(
        tenant_id=TenantId(new_id()), broker=BrokerName.KITE, credentials=KITE, now=NOW
    )
    connection.complete_connect(
        access_token="tok", refresh_token=None, profile=None, now=NOW, expires_at=expires_at
    )
    return connection


class TestKnownExpiry:
    def test_before_the_logout_the_token_is_served(self) -> None:
        connection = _active_kite(NOW + timedelta(hours=20))
        assert connection.require_access_token(NOW + timedelta(hours=19)) == "tok"

    def test_after_the_logout_it_is_expired_without_asking_zerodha(self) -> None:
        connection = _active_kite(NOW + timedelta(hours=20))
        assert connection.has_lapsed(NOW + timedelta(hours=20))
        with pytest.raises(ConnectionExpiredError):
            connection.require_access_token(NOW + timedelta(hours=21))

    def test_without_an_expiry_nothing_lapses(self) -> None:
        connection = _active_kite(None)
        assert not connection.has_lapsed(NOW + timedelta(days=30))


# --- the use cases -----------------------------------------------------------


class FakeRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[TenantId, BrokerName], BrokerConnection] = {}
        self.writes: list[tuple[BrokerName, ConnectionStatus]] = []

    async def find(self, tenant_id: TenantId, broker: BrokerName) -> BrokerConnection | None:
        return self.rows.get((tenant_id, broker))

    async def find_others(self, tenant_id: TenantId, broker: BrokerName) -> list[BrokerConnection]:
        return [c for (t, b), c in self.rows.items() if t == tenant_id and b is not broker]

    async def add(self, connection: BrokerConnection) -> None:
        self.rows[(connection.tenant_id, connection.broker)] = connection
        self.writes.append((connection.broker, connection.status))

    async def update(self, connection: BrokerConnection) -> None:
        self.rows[(connection.tenant_id, connection.broker)] = connection
        self.writes.append((connection.broker, connection.status))


class FakeStates:
    def __init__(self, pending: PendingConnection | None) -> None:
        self.pending = pending

    async def consume(self, state: str) -> PendingConnection | None:
        pending, self.pending = self.pending, None
        return pending


class FakeOAuth:
    def __init__(self, user_id: str = "AB1234", *, revoke_fails: bool = False) -> None:
        self.user_id = user_id
        self.revoke_fails = revoke_fails
        self.revoked: list[str] = []

    async def exchange_code(self, **_: object) -> BrokerTokens:
        return BrokerTokens(access_token="new-tok", expires_at=NOW + timedelta(hours=20))

    async def fetch_profile(self, **_: object) -> BrokerProfile:
        return BrokerProfile(broker_user_id=self.user_id, display_name="Trader")

    async def revoke_token(self, *, credentials: BrokerCredentials, access_token: str) -> None:
        self.revoked.append(access_token)
        if self.revoke_fails:
            raise RuntimeError("zerodha down")


class FakeUow:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class FakeCache:
    def __init__(self) -> None:
        self.invalidated: list[BrokerName] = []

    async def invalidate(self, tenant_id: TenantId, broker: BrokerName) -> None:
        self.invalidated.append(broker)


class FixedClock:
    def now(self) -> datetime:
        return NOW


TENANT = TenantId(new_id())
USER = UserId(new_id())
POLICY = ConnectPolicy(redirect_uri="https://example.test/settings/broker/kite/callback")


def _pending(broker: BrokerName) -> PendingConnection:
    return PendingConnection(tenant_id=TENANT, user_id=USER, broker=broker)


def _seed(repo: FakeRepository, broker: BrokerName, *, active: bool, client_id: str | None = None):
    credentials = KITE if broker is BrokerName.KITE else FYERS
    connection = BrokerConnection.start(
        tenant_id=TENANT, broker=broker, credentials=credentials, client_id=client_id, now=NOW
    )
    if active:
        connection.complete_connect(
            access_token=f"{broker.value}-old", refresh_token=None, profile=None, now=NOW
        )
    repo.rows[(TENANT, broker)] = connection
    return connection


def _complete(
    repo: FakeRepository,
    oauth: FakeOAuth,
    broker: BrokerName,
    *,
    revokers: dict[BrokerName, FakeOAuth] | None = None,
) -> tuple[CompleteConnect, FakeUow, FakeCache]:
    uow, cache = FakeUow(), FakeCache()
    use_case = CompleteConnect(
        connections=repo,  # type: ignore[arg-type]
        oauth=oauth,  # type: ignore[arg-type]
        states=FakeStates(_pending(broker)),  # type: ignore[arg-type]
        clock=FixedClock(),
        uow=uow,
        policy=POLICY,
        cache=cache,
        revokers=revokers,  # type: ignore[arg-type]
    )
    return use_case, uow, cache


class TestOneActiveBroker:
    async def test_connecting_kite_disconnects_fyers_and_keeps_its_keys(self) -> None:
        repo = FakeRepository()
        fyers = _seed(repo, BrokerName.FYERS, active=True)
        _seed(repo, BrokerName.KITE, active=False)
        use_case, uow, cache = _complete(repo, FakeOAuth(), BrokerName.KITE)

        view = await use_case(CompleteConnectCommand(code="rt", state="s", broker=BrokerName.KITE))

        assert view.status == ConnectionStatus.ACTIVE.value
        assert fyers.status is ConnectionStatus.PENDING
        assert fyers.access_token is None
        assert fyers.has_credentials
        assert uow.commits == 1
        assert set(cache.invalidated) == {BrokerName.KITE, BrokerName.FYERS}

    async def test_the_displaced_row_is_written_before_the_new_one(self) -> None:
        """The partial unique index allows one active row per tenant, so the
        order of writes inside the transaction matters."""
        repo = FakeRepository()
        _seed(repo, BrokerName.FYERS, active=True)
        _seed(repo, BrokerName.KITE, active=False)
        use_case, _, _ = _complete(repo, FakeOAuth(), BrokerName.KITE)

        await use_case(CompleteConnectCommand(code="rt", state="s", broker=BrokerName.KITE))

        assert repo.writes == [
            (BrokerName.FYERS, ConnectionStatus.PENDING),
            (BrokerName.KITE, ConnectionStatus.ACTIVE),
        ]

    async def test_connecting_fyers_ends_the_kite_session_at_zerodha(self) -> None:
        repo = FakeRepository()
        _seed(repo, BrokerName.KITE, active=True)
        _seed(repo, BrokerName.FYERS, active=False)
        kite_oauth = FakeOAuth()
        use_case, _, _ = _complete(
            repo, FakeOAuth(), BrokerName.FYERS, revokers={BrokerName.KITE: kite_oauth}
        )

        await use_case(CompleteConnectCommand(code="c", state="s", broker=BrokerName.FYERS))

        assert kite_oauth.revoked == ["kite-old"]
        assert repo.rows[(TENANT, BrokerName.KITE)].status is ConnectionStatus.PENDING

    async def test_a_failed_remote_revoke_does_not_block_the_switch(self) -> None:
        repo = FakeRepository()
        _seed(repo, BrokerName.KITE, active=True)
        _seed(repo, BrokerName.FYERS, active=False)
        use_case, uow, _ = _complete(
            repo,
            FakeOAuth(),
            BrokerName.FYERS,
            revokers={BrokerName.KITE: FakeOAuth(revoke_fails=True)},
        )

        await use_case(CompleteConnectCommand(code="c", state="s", broker=BrokerName.FYERS))

        assert repo.rows[(TENANT, BrokerName.FYERS)].is_connected
        assert not repo.rows[(TENANT, BrokerName.KITE)].is_connected
        assert uow.commits == 1

    async def test_an_inactive_other_broker_is_left_alone(self) -> None:
        repo = FakeRepository()
        fyers = _seed(repo, BrokerName.FYERS, active=False)
        _seed(repo, BrokerName.KITE, active=False)
        use_case, _, _ = _complete(repo, FakeOAuth(), BrokerName.KITE)

        await use_case(CompleteConnectCommand(code="rt", state="s", broker=BrokerName.KITE))

        assert (BrokerName.FYERS, ConnectionStatus.PENDING) not in repo.writes
        assert fyers.has_credentials


class TestAccountBinding:
    async def test_the_wrong_account_is_refused_and_nothing_is_stored(self) -> None:
        repo = FakeRepository()
        fyers = _seed(repo, BrokerName.FYERS, active=True)
        kite = _seed(repo, BrokerName.KITE, active=False, client_id="AB1234")
        oauth = FakeOAuth(user_id="ZZ9999")
        use_case, uow, _ = _complete(repo, oauth, BrokerName.KITE)

        with pytest.raises(BrokerAccountMismatchError):
            await use_case(CompleteConnectCommand(code="rt", state="s", broker=BrokerName.KITE))

        assert kite.access_token is None
        assert kite.status is ConnectionStatus.PENDING
        assert fyers.is_connected  # the working broker is untouched
        assert repo.writes == []
        assert uow.commits == 0
        # ...and the session Zerodha minted for the wrong account is ended.
        assert oauth.revoked == ["new-tok"]

    async def test_the_right_account_connects(self) -> None:
        repo = FakeRepository()
        _seed(repo, BrokerName.KITE, active=False, client_id="AB1234")
        use_case, _, _ = _complete(repo, FakeOAuth(user_id="ab1234"), BrokerName.KITE)

        await use_case(CompleteConnectCommand(code="rt", state="s", broker=BrokerName.KITE))

        connection = repo.rows[(TENANT, BrokerName.KITE)]
        assert connection.is_connected
        assert connection.expires_at == NOW + timedelta(hours=20)


class TestSaveKiteCredentials:
    async def test_kite_keys_and_client_id_are_saved(self) -> None:
        repo, uow, cache = FakeRepository(), FakeUow(), FakeCache()
        use_case = SaveCredentials(
            connections=repo,  # type: ignore[arg-type]
            clock=FixedClock(),
            uow=uow,
            policy=POLICY,
            cache=cache,
        )

        await use_case(
            SaveCredentialsCommand(
                tenant_id=TENANT,
                app_id=KITE_KEY.upper(),
                secret=KITE_SECRET,
                broker=BrokerName.KITE,
                client_id="ab1234",
            )
        )

        saved = repo.rows[(TENANT, BrokerName.KITE)]
        assert saved.credentials == KITE
        assert saved.client_id == "AB1234"
        assert cache.invalidated == [BrokerName.KITE]
