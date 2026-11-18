"""Per-user Trade Buddy: WhatsApp connect, secrets that never leak, and the
worker's write batching and shared ATR.

The database-backed halves — the encrypted target, the per-user store and its
isolation — are exercised against Postgres in
``tests/integration/postgresql/test_trade_buddy_per_user.py``.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import pytest

from chartnexus.contexts.trade_buddy.application.channels import (
    WHATSAPP_LABEL,
    WHATSAPP_WELCOME,
    ConnectWhatsApp,
    ConnectWhatsAppCommand,
    SendChannelTest,
)
from chartnexus.contexts.trade_buddy.application.ports import RuntimeState
from chartnexus.contexts.trade_buddy.domain.channel import (
    AlertChannel,
    AlertConnection,
    normalise_phone,
)
from chartnexus.contexts.trade_buddy.domain.errors import (
    ChannelVerificationError,
    InvalidPhoneNumberError,
)
from chartnexus.contexts.trade_buddy.domain.level import LevelBands, LevelMark, LevelRole
from chartnexus.contexts.trade_buddy.domain.state import LevelState, LevelWatcher
from chartnexus.infrastructure.notifications.whatsapp.callmebot import CallMeBotNotifier
from chartnexus.infrastructure.trade_buddy.atr_cache import SessionAtrCache
from chartnexus.infrastructure.trade_buddy.clock import FakeClock
from chartnexus.infrastructure.trade_buddy.coalescing_store import CoalescingLevelStore
from chartnexus.infrastructure.trade_buddy.telegram_notifier import TelegramNotifier
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId
from tests.unit.trade_buddy.conftest import MemoryLevelStore
from tests.unit.trade_buddy.test_channels import FakeSender, MemoryChannels

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
USER = UserId(uuid.uuid4())
TENANT = TenantId(uuid.uuid4())
PHONE = "+919876543210"
API_KEY = "callmebot-key-123456"


# -- phone numbers ------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+919876543210", "+919876543210"),
        ("+91 98765 43210", "+919876543210"),
        ("+91-98765-43210", "+919876543210"),
        ("0091 98765 43210", "+919876543210"),
        ("+1 (415) 555-0100", "+14155550100"),
        ("98765 43210", None),  # no country code — refused, not guessed
        ("+0 1234 5678", None),  # country codes never start with 0
        ("+91 98765", None),  # too short
        ("not a number", None),
    ],
)
def test_phone_numbers_are_normalised_or_refused(raw: str, expected: str | None) -> None:
    assert normalise_phone(raw) == expected


def test_a_target_is_shown_by_its_last_four_characters_only() -> None:
    connection = AlertConnection.create(
        user_id=USER,
        tenant_id=TENANT,
        channel=AlertChannel.WHATSAPP,
        secret=API_KEY,
        label=None,
        now=NOW,
    )
    connection.link_target(PHONE, NOW)

    assert connection.masked_target == "…3210"
    assert PHONE not in (connection.masked_target or "")
    assert API_KEY not in (connection.masked_secret or "")


# -- connecting WhatsApp ------------------------------------------------------


def _connect(repo: MemoryChannels, sender: FakeSender) -> ConnectWhatsApp:
    return ConnectWhatsApp(repository=repo, sender=sender, clock=FakeClock(NOW))


def _command(phone: str = PHONE, api_key: str = API_KEY) -> ConnectWhatsAppCommand:
    return ConnectWhatsAppCommand(user_id=USER, tenant_id=TENANT, phone=phone, api_key=api_key)


class TestConnectWhatsApp:
    async def test_it_proves_delivery_then_stores_a_ready_connection(self):
        repo, sender = MemoryChannels(), FakeSender()

        connection = await _connect(repo, sender)(_command(phone="+91 98765 43210"))

        assert sender.sent == [(PHONE, WHATSAPP_WELCOME)]
        assert connection.ready
        assert connection.target == PHONE  # normalised
        assert connection.secret == API_KEY
        assert repo.rows[(USER, AlertChannel.WHATSAPP)] is connection

    async def test_the_label_never_carries_the_number(self):
        repo, sender = MemoryChannels(), FakeSender()
        connection = await _connect(repo, sender)(_command())

        assert connection.label == WHATSAPP_LABEL
        assert "9876" not in connection.label

    async def test_an_invalid_number_is_refused_before_anything_is_sent(self):
        repo, sender = MemoryChannels(), FakeSender()

        with pytest.raises(InvalidPhoneNumberError) as raised:
            await _connect(repo, sender)(_command(phone="55512 34567"))

        assert sender.sent == []
        assert repo.rows == {}
        # The error is shown to the user and logged: it must not echo the number.
        assert "55512" not in str(raised.value)

    async def test_a_failed_welcome_stores_nothing(self):
        repo, sender = MemoryChannels(), FakeSender(send_fails=True)

        with pytest.raises(ChannelVerificationError):
            await _connect(repo, sender)(_command())

        assert repo.rows == {}

    async def test_a_blank_key_is_refused(self):
        repo, sender = MemoryChannels(), FakeSender()

        with pytest.raises(ChannelVerificationError):
            await _connect(repo, sender)(_command(api_key="   "))
        assert sender.sent == []

    async def test_reconnecting_replaces_the_key_and_number(self):
        repo, sender = MemoryChannels(), FakeSender()
        first = await _connect(repo, sender)(_command())

        second = await _connect(repo, sender)(_command(phone="+14155550100", api_key="new-key-1"))

        assert second.id == first.id
        assert second.target == "+14155550100"
        assert second.secret == "new-key-1"
        assert len(repo.rows) == 1

    async def test_the_channel_test_uses_the_whatsapp_sender_and_plain_text(self):
        repo, telegram, whatsapp = MemoryChannels(), FakeSender(), FakeSender()
        await _connect(repo, whatsapp)(_command())
        whatsapp.sent.clear()

        test = SendChannelTest(
            repository=repo, sender=telegram, senders={AlertChannel.WHATSAPP: whatsapp}
        )
        await test(USER, AlertChannel.WHATSAPP)

        assert telegram.sent == []
        [(target, text)] = whatsapp.sent
        assert target == PHONE
        assert "<" not in text  # no HTML for a channel that cannot render it


# -- errors never carry a secret ---------------------------------------------


def _client(handler) -> httpx.AsyncClient:  # type: ignore[no-untyped-def]
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestCallMeBotErrorsCarryNoSecrets:
    """CallMeBot takes the key and number in the query string, and an httpx
    error's text includes the URL. Every error must be rebuilt without it."""

    async def _error(self, handler) -> BaseException:  # type: ignore[no-untyped-def]
        async with _client(handler) as client:
            notifier = CallMeBotNotifier(client, phone=PHONE, api_key=API_KEY)
            with pytest.raises(httpx.HTTPError) as raised:
                await notifier.send("hello")
        return raised.value

    async def test_a_transport_failure(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        error = await self._error(handler)
        self._assert_clean(error)

    async def test_an_http_error_status(self):
        error = await self._error(lambda _request: httpx.Response(500, text="boom"))
        self._assert_clean(error)

    async def test_a_rejected_key(self):
        error = await self._error(
            lambda _request: httpx.Response(200, text="Error: APIKey is invalid")
        )
        self._assert_clean(error)

    @staticmethod
    def _assert_clean(error: BaseException) -> None:
        text = f"{error} {error!r}"
        assert API_KEY not in text
        assert PHONE.lstrip("+") not in text
        # Nothing chained underneath that a logger could print instead.
        assert error.__cause__ is None
        assert error.__context__ is None or error.__suppress_context__


class TestTelegramErrorsCarryNoToken:
    async def test_a_transport_failure_does_not_include_the_bot_url(self):
        token = "123456:SECRET-bot-token"

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        async with _client(handler) as client:
            notifier = TelegramNotifier(client, bot_token=token, chat_id="42")
            with pytest.raises(httpx.HTTPError) as raised:
                await notifier.send("hello")

        assert token not in f"{raised.value} {raised.value!r}"
        assert raised.value.__cause__ is None


# -- the worker's write batching ---------------------------------------------


@dataclass
class CountingStore(MemoryLevelStore):
    watcher_writes: int = 0
    runtime_writes: int = 0

    async def save_watchers(self, symbol, watchers):  # type: ignore[no-untyped-def]
        self.watcher_writes += 1
        await super().save_watchers(symbol, watchers)

    async def save_runtime(self, symbol, state):  # type: ignore[no-untyped-def]
        self.runtime_writes += 1
        await super().save_runtime(symbol, state)


@dataclass
class Tick:
    value: float = 0.0

    def __call__(self) -> float:
        return self.value


BANDS = LevelBands(touch=6.0, approach=25.0, break_buffer=12.0, confirm_hold_seconds=20.0)
MARK = LevelMark(label="R1", price=24_700.0, role=LevelRole.RESISTANCE)


def _watchers(state: LevelState = LevelState.IDLE) -> tuple[LevelWatcher, ...]:
    watcher = LevelWatcher(symbol="NIFTY", mark=MARK, bands=BANDS)
    watcher.state = state
    return (watcher,)


def _runtime(price: float, *, budget: dict[str, object] | None = None) -> RuntimeState:
    return RuntimeState(
        last_tick_at=NOW, last_price=price, session=date(2026, 11, 18), level_budget=budget or {}
    )


class TestCoalescingStore:
    def _store(self) -> tuple[CoalescingLevelStore, CountingStore, Tick]:
        inner, clock = CountingStore(), Tick()
        return CoalescingLevelStore(inner, interval_seconds=5.0, monotonic=clock), inner, clock

    async def test_quiet_ticks_are_written_at_most_once_per_interval(self):
        store, inner, clock = self._store()
        await store.save_watchers("NIFTY", _watchers())
        await store.save_runtime("NIFTY", _runtime(100.0))
        written = inner.runtime_writes

        for second in range(1, 5):  # four quiet ticks inside the interval
            clock.value = float(second)
            await store.save_watchers("NIFTY", _watchers())
            await store.save_runtime("NIFTY", _runtime(100.0 + second))

        assert inner.runtime_writes == written

        clock.value = 6.0
        await store.save_runtime("NIFTY", _runtime(106.0))
        assert inner.runtime_writes == written + 1
        assert (await inner.load_runtime("NIFTY")).last_price == 106.0

    async def test_a_state_change_is_written_at_once(self):
        store, inner, clock = self._store()
        await store.save_watchers("NIFTY", _watchers())
        clock.value = 1.0

        await store.save_watchers("NIFTY", _watchers(LevelState.TOUCHED))

        assert inner.watchers["NIFTY"][0].state is LevelState.TOUCHED

    async def test_an_alert_counter_change_is_written_at_once(self):
        """Losing it to a crash would let a restart send the same alert again."""
        store, inner, clock = self._store()
        await store.save_runtime("NIFTY", _runtime(100.0))
        clock.value = 1.0

        await store.save_runtime("NIFTY", _runtime(101.0, budget={"sent_today": {"R1": 1}}))

        assert inner.runtime["NIFTY"].level_budget == {"sent_today": {"R1": 1}}

    async def test_flush_writes_what_was_held(self):
        store, inner, clock = self._store()
        await store.save_runtime("NIFTY", _runtime(100.0))
        clock.value = 1.0
        await store.save_runtime("NIFTY", _runtime(150.0))

        await store.flush_all()

        assert inner.runtime["NIFTY"].last_price == 150.0

    async def test_a_reset_is_not_undone_by_a_late_flush(self):
        store, inner, clock = self._store()
        await store.save_watchers("NIFTY", _watchers())
        clock.value = 1.0
        await store.save_watchers("NIFTY", _watchers())  # held

        await store.reset_day("NIFTY")
        await store.flush_all()

        assert "NIFTY" not in inner.watchers or inner.watchers["NIFTY"] == _watchers()
        assert store._watchers == {}


# -- shared ATR ---------------------------------------------------------------


@dataclass
class CountingAtr:
    value: float | None = 250.0
    calls: int = 0
    delay: float = 0.0

    async def atr(self, symbol: str, *, period: int = 14) -> float | None:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.value


class TestSessionAtrCache:
    async def test_many_users_cost_one_fetch_per_instrument_per_day(self):
        inner = CountingAtr()
        cache = SessionAtrCache(inner, today=lambda: date(2026, 11, 18))

        results = [await cache.atr("NIFTY") for _ in range(100)]

        assert set(results) == {250.0}
        assert inner.calls == 1

    async def test_concurrent_first_requests_share_one_fetch(self):
        inner = CountingAtr(delay=0.01)
        cache = SessionAtrCache(inner, today=lambda: date(2026, 11, 18))

        await asyncio.gather(*(cache.atr("NIFTY") for _ in range(20)))

        assert inner.calls == 1

    async def test_a_new_day_fetches_again(self):
        inner, day = CountingAtr(), {"d": date(2026, 11, 18)}
        cache = SessionAtrCache(inner, today=lambda: day["d"])
        await cache.atr("NIFTY")

        day["d"] = date(2026, 11, 19)
        await cache.atr("NIFTY")

        assert inner.calls == 2

    async def test_a_failed_fetch_is_not_cached(self):
        inner = CountingAtr(value=None)
        cache = SessionAtrCache(inner, today=lambda: date(2026, 11, 18))
        assert await cache.atr("NIFTY") is None

        inner.value = 300.0
        assert await cache.atr("NIFTY") == 300.0
        assert inner.calls == 2

    async def test_instruments_are_cached_separately(self):
        inner = CountingAtr()
        cache = SessionAtrCache(inner, today=lambda: date(2026, 11, 18))
        await cache.atr("NIFTY")
        await cache.atr("SENSEX")
        assert inner.calls == 2
