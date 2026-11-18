"""Per-user Trade Buddy against a real Postgres: isolation, encryption, cleanup.

What the unit tests cannot show, because it lives in SQL and in the HTTP stack:

* **Isolation over HTTP.** Two signed-in users mark the same index; each sees
  and changes only their own levels.
* **Encryption at rest.** A WhatsApp number and API key are stored as
  ciphertext, bound to their user: a row moved to another user stops
  decrypting rather than delivering to the wrong person.
* **Cleanup.** Deleting a user deletes their state and their channels.
* **Concurrent writes.** The API and the worker both write one row; the
  ``FOR UPDATE`` read-modify-write must not lose either write.

Every background loop is switched off for the app these tests build, so a test
run never watches or alerts on anybody's real levels.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from chartnexus.bootstrap.settings import Settings
from chartnexus.contexts.trade_buddy.application.ports import AlertRecord
from chartnexus.contexts.trade_buddy.domain.channel import AlertChannel, AlertConnection
from chartnexus.contexts.trade_buddy.domain.events import AlertKind
from chartnexus.contexts.trade_buddy.domain.level import LevelBands, LevelMark, LevelRole
from chartnexus.entrypoints.main_api import create_app
from chartnexus.infrastructure.persistence.postgresql.repositories.trade_buddy.alert_channel_repository import (
    SqlAlchemyAlertChannelRepository,
)
from chartnexus.infrastructure.persistence.postgresql.repositories.trade_buddy.watch_state_repository import (
    PostgresLevelStore,
    find_watch_targets,
)
from chartnexus.infrastructure.persistence.postgresql.session import Database
from chartnexus.infrastructure.security.encryption import AesGcmCipher
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId

pytestmark = pytest.mark.integration

DSN = "postgresql+asyncpg://chartnexus:chartnexus@localhost:5433/chartnexus"
PASSWORD = "a-perfectly-fine-password"
API = "/api/v1/trade-buddy"
BANDS = LevelBands(touch=6.0, approach=25.0, break_buffer=12.0, confirm_hold_seconds=20.0)
PHONE = "+919876501234"
API_KEY = "per-user-callmebot-key"

_LOOPS_OFF = {"in_process": False}


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings(
        environment="local",
        database={"url": DSN},
        redis={"url": "redis://localhost:6381/0", "key_prefix": f"it-{uuid.uuid4().hex[:8]}"},
        auth={"jwt_signing_key": "integration-test-signing-key-long-enough"},
        security={"cookie_secure": False},
        market={"ingest_in_process": False},
        trade_buddy={"enabled": False, "in_process": False},
        hugin=_LOOPS_OFF,
        mme100=_LOOPS_OFF,
        report=_LOOPS_OFF,
        catalog=_LOOPS_OFF,
        futures_oi=_LOOPS_OFF,
        futures_history=_LOOPS_OFF,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
async def database() -> AsyncIterator[Database]:
    from chartnexus.bootstrap.settings import DatabaseSettings  # noqa: PLC0415

    db = Database.create(DatabaseSettings(url=DSN), use_pool=False)  # type: ignore[arg-type]
    try:
        yield db
    finally:
        await db.dispose()


class User:
    """One signed-up account and the headers its requests need."""

    def __init__(self, client: TestClient) -> None:
        self.email = f"tb-{uuid.uuid4().hex[:12]}@example.com"
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": self.email,
                "password": PASSWORD,
                "phone": f"9{secrets.randbelow(1_000_000_000):09d}",
            },
        )
        assert response.status_code == 201, response.text
        self.headers = {"X-CSRF-Token": response.json()["tokens"]["csrf_token"]}
        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200, me.text
        self.id = UserId(uuid.UUID(me.json()["id"]))

    def use(self, client: TestClient) -> TestClient:
        """Make ``client`` this user's session (one cookie jar, so switch)."""
        response = client.post(
            "/api/v1/auth/login", json={"identifier": self.email, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        self.headers = {"X-CSRF-Token": response.json()["tokens"]["csrf_token"]}
        return client


def _levels(*prices: float) -> list[dict[str, object]]:
    return [
        {"label": f"R{i + 1}", "price": price, "role": "resistance"}
        for i, price in enumerate(prices)
    ]


# -- isolation over HTTP ------------------------------------------------------


def test_trade_buddy_routes_refuse_anonymous_callers(client: TestClient) -> None:
    for path in ("/levels?symbol=NIFTY", "/channels", "/state?symbol=NIFTY", "/watchlist"):
        assert client.get(f"{API}{path}").status_code == 401, path


def test_two_users_mark_the_same_index_and_see_only_their_own(client: TestClient) -> None:
    alice, bob = User(client), User(client)

    alice.use(client)
    put = client.put(
        f"{API}/levels", json={"symbol": "NIFTY", "levels": _levels(24_700)}, headers=alice.headers
    )
    assert put.status_code == 200, put.text

    bob.use(client)
    assert client.get(f"{API}/levels?symbol=NIFTY").json()["levels"] == []
    put = client.put(
        f"{API}/levels", json={"symbol": "NIFTY", "levels": _levels(25_100)}, headers=bob.headers
    )
    assert put.status_code == 200, put.text

    alice.use(client)
    assert [lvl["price"] for lvl in client.get(f"{API}/levels?symbol=NIFTY").json()["levels"]] == [
        24_700
    ]

    bob.use(client)
    assert [lvl["price"] for lvl in client.get(f"{API}/levels?symbol=NIFTY").json()["levels"]] == [
        25_100
    ]


def test_one_users_quick_reset_does_not_touch_another(client: TestClient) -> None:
    alice, bob = User(client), User(client)
    for user, price in ((alice, 24_700), (bob, 25_100)):
        user.use(client)
        client.put(
            f"{API}/levels",
            json={"symbol": "NIFTY", "levels": _levels(price)},
            headers=user.headers,
        )

    alice.use(client)
    reset = client.post(f"{API}/reset?symbol=NIFTY", headers=alice.headers)
    assert reset.status_code == 204, reset.text
    assert client.get(f"{API}/levels?symbol=NIFTY").json()["levels"] == []

    bob.use(client)
    assert len(client.get(f"{API}/levels?symbol=NIFTY").json()["levels"]) == 1


def test_channels_are_listed_per_user_and_never_in_full(
    client: TestClient, settings: Settings
) -> None:
    alice, bob = User(client), User(client)
    # Stored through the real repository and cipher — the HTTP connect would
    # need CallMeBot to answer.
    asyncio.run(_store_whatsapp(settings, alice.id))

    alice.use(client)
    rows = {row["channel"]: row for row in client.get(f"{API}/channels").json()["channels"]}
    whatsapp = rows["whatsapp"]
    assert whatsapp["ready"] is True
    assert whatsapp["target"] == "…1234"
    body = client.get(f"{API}/channels").text
    assert PHONE not in body
    assert API_KEY not in body

    bob.use(client)
    rows = {row["channel"]: row for row in client.get(f"{API}/channels").json()["channels"]}
    assert rows["whatsapp"]["configured"] is False


async def _store_whatsapp(settings: Settings, user_id: UserId) -> None:
    db = Database.create(settings.database, use_pool=False)
    try:
        repo = _repo(db, settings)
        connection = AlertConnection.create(
            user_id=user_id,
            tenant_id=await _tenant_of(db, user_id),
            channel=AlertChannel.WHATSAPP,
            secret=API_KEY,
            label="WhatsApp (CallMeBot)",
            now=_now(),
        )
        connection.link_target(PHONE, _now())
        await repo.upsert(connection)
    finally:
        await db.dispose()


# -- encryption at rest -------------------------------------------------------


def _repo(db: Database, settings: Settings) -> SqlAlchemyAlertChannelRepository:
    cipher = AesGcmCipher.derive(
        settings.security.encryption_key.get_secret_value(), purpose="messaging-credentials"
    )
    return SqlAlchemyAlertChannelRepository(db, cipher)


def _now():  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime  # noqa: PLC0415

    return datetime.now(UTC)


async def _tenant_of(db: Database, user_id: UserId) -> TenantId:
    async with db.read_session() as session:
        tenant = (
            await session.execute(
                sa.text("select tenant_id from users where id = :id"), {"id": user_id}
            )
        ).scalar_one()
    return TenantId(tenant)


async def test_the_number_and_key_are_ciphertext_at_rest(
    client: TestClient, settings: Settings, database: Database
) -> None:
    alice = User(client)
    await _store_whatsapp(settings, alice.id)

    async with database.read_session() as session:
        row = (
            await session.execute(
                sa.text(
                    "select secret_enc, target_enc from trade_buddy_channels "
                    "where user_id = :id and channel = 'whatsapp'"
                ),
                {"id": alice.id},
            )
        ).one()

    for value in row:
        assert value.startswith("mcv1.")
        assert PHONE not in value
        assert API_KEY not in value
    ready = await _repo(database, settings).find_ready(alice.id)
    assert [(c.channel, c.target, c.secret) for c in ready] == [
        (AlertChannel.WHATSAPP, PHONE, API_KEY)
    ]


async def test_a_row_moved_to_another_user_stops_decrypting(
    client: TestClient, settings: Settings, database: Database
) -> None:
    """The AAD binds each value to its user: write access to the table is not
    enough to redirect someone's alerts to yourself, or theirs to you."""
    alice, mallory = User(client), User(client)
    await _store_whatsapp(settings, alice.id)

    async with database.session() as session:
        await session.execute(
            sa.text(
                "update trade_buddy_channels set user_id = :to where user_id = :from_ "
                "and channel = 'whatsapp'"
            ),
            {"to": mallory.id, "from_": alice.id},
        )

    assert await _repo(database, settings).find_ready(mallory.id) == ()
    moved = await _repo(database, settings).find(mallory.id, AlertChannel.WHATSAPP)
    assert moved is not None
    assert moved.secret == ""
    assert moved.target is None


# -- the state store ----------------------------------------------------------


async def test_the_store_is_scoped_to_its_user(client: TestClient, database: Database) -> None:
    alice, bob = User(client), User(client)
    alice_store = PostgresLevelStore(
        database, alice.id, await _tenant_of(database, alice.id), BANDS
    )
    bob_store = PostgresLevelStore(database, bob.id, await _tenant_of(database, bob.id), BANDS)
    mark = LevelMark(label="S1", price=24_000.0, role=LevelRole.SUPPORT)

    await alice_store.save_marks("NIFTY", (mark,), _now().date())

    assert (await alice_store.load_marks("NIFTY")).marks == (mark,)
    assert (await bob_store.load_marks("NIFTY")).marks == ()
    targets = await find_watch_targets(database, ("NIFTY",))
    assert (alice.id, "NIFTY") in {(t.user_id, t.symbol) for t in targets}
    assert (bob.id, "NIFTY") not in {(t.user_id, t.symbol) for t in targets}


async def test_concurrent_writes_to_one_row_are_not_lost(
    client: TestClient, database: Database
) -> None:
    """The worker appending alerts while the API saves overrides, on one row."""
    alice = User(client)
    store = PostgresLevelStore(database, alice.id, await _tenant_of(database, alice.id), BANDS)
    session = _now().date()

    def record(i: int) -> AlertRecord:
        return AlertRecord(
            kind=AlertKind.TOUCHED,
            label=f"R{i}",
            level_price=24_700.0 + i,
            price=24_700.0 + i,
            role_before=LevelRole.RESISTANCE,
            role_after=LevelRole.RESISTANCE,
            at=_now(),
            session=session,
        )

    await asyncio.gather(*(store.append_alert("NIFTY", record(i)) for i in range(20)))

    assert len(await store.load_alerts("NIFTY", session)) == 20


async def test_deleting_a_user_deletes_their_state_and_channels(
    client: TestClient, settings: Settings, database: Database
) -> None:
    alice = User(client)
    store = PostgresLevelStore(database, alice.id, await _tenant_of(database, alice.id), BANDS)
    await store.save_marks(
        "NIFTY", (LevelMark(label="R1", price=1.0, role=LevelRole.RESISTANCE),), _now().date()
    )
    await _store_whatsapp(settings, alice.id)

    async with database.session() as session:
        # Sessions reference the user too; clear them so the user row can go.
        await session.execute(
            sa.text("delete from refresh_sessions where user_id = :id"), {"id": alice.id}
        )
        await session.execute(sa.text("delete from users where id = :id"), {"id": alice.id})

    async with database.read_session() as session:
        for table in ("trade_buddy_watch_states", "trade_buddy_channels"):
            left = (
                await session.execute(
                    sa.text(f"select count(*) from {table} where user_id = :id"),  # noqa: S608
                    {"id": alice.id},
                )
            ).scalar_one()
            assert left == 0, table
