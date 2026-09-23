"""DeliverText gating + the connect/link/test use cases, over fakes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from marketcompass.contexts.messaging.application.deliver import DeliverText
from marketcompass.contexts.messaging.application.ports import ChannelIdentity
from marketcompass.contexts.messaging.application.use_cases import (
    ConnectTelegram,
    ConnectTelegramCommand,
    DetectTelegramChat,
    DetectTelegramChatCommand,
    SendTestMessage,
)
from marketcompass.contexts.messaging.domain.channel import Channel, ChannelConnection
from marketcompass.contexts.messaging.domain.errors import ChannelVerificationError
from marketcompass.infrastructure.time.clock import FixedClock
from marketcompass.shared_kernel.types.identifiers import TenantId, UserId

NOW = datetime(2026, 8, 23, tzinfo=UTC)
USER = UserId(uuid.uuid4())
TENANT = TenantId(uuid.uuid4())
_TOKEN = "123456789:AAqwertyuiopasdfghjklzxcvbnm12345678"


class _FakeRepo:
    def __init__(self, connections: list[ChannelConnection] | None = None) -> None:
        self._rows = {(c.user_id, c.channel): c for c in (connections or [])}

    async def find(self, user_id: UserId, channel: Channel) -> ChannelConnection | None:
        return self._rows.get((user_id, channel))

    async def find_all(self, user_id: UserId) -> tuple[ChannelConnection, ...]:
        return tuple(c for (u, _), c in self._rows.items() if u == user_id)

    async def upsert(self, connection: ChannelConnection) -> None:
        self._rows[(connection.user_id, connection.channel)] = connection

    async def delete(self, user_id: UserId, channel: Channel) -> None:
        self._rows.pop((user_id, channel), None)


class _FakeSender:
    def __init__(
        self, *, username: str = "@bot", target: str | None = "555", fail: bool = False
    ) -> None:
        self._username = username
        self._target = target
        self._fail = fail
        self.sent: list[tuple[str, str, str]] = []

    @property
    def channel(self) -> Channel:
        return Channel.TELEGRAM

    async def verify(self, secret: str) -> ChannelIdentity:
        return ChannelIdentity(label=self._username)

    async def detect_target(self, secret: str) -> str | None:
        return self._target

    async def send(self, secret: str, target: str, text: str) -> None:
        if self._fail:
            raise ChannelVerificationError("boom")
        self.sent.append((secret, target, text))


def _ready(user_id: UserId = USER, *, enabled: bool = True) -> ChannelConnection:
    conn = ChannelConnection.create(
        user_id=user_id,
        tenant_id=TENANT,
        channel=Channel.TELEGRAM,
        secret=_TOKEN,
        label="@bot",
        now=NOW,
    )
    conn.link_target("555", NOW)
    conn.set_enabled(enabled, NOW)
    return conn


# -- DeliverText ------------------------------------------------------------


async def test_deliver_sends_only_to_ready_channels() -> None:
    sender = _FakeSender()
    repo = _FakeRepo([_ready()])
    count = await DeliverText(repository=repo, senders={Channel.TELEGRAM: sender})(
        USER, "hello", source="test"
    )
    assert count == 1
    assert sender.sent[0][2] == "hello"


async def test_deliver_skips_disabled_channel() -> None:
    sender = _FakeSender()
    repo = _FakeRepo([_ready(enabled=False)])
    count = await DeliverText(repository=repo, senders={Channel.TELEGRAM: sender})(
        USER, "hi", source="test"
    )
    assert count == 0
    assert sender.sent == []


async def test_deliver_swallows_a_send_failure() -> None:
    repo = _FakeRepo([_ready()])
    sender = _FakeSender(fail=True)
    # Must not raise — a failed channel is logged and counted as not delivered.
    count = await DeliverText(repository=repo, senders={Channel.TELEGRAM: sender})(
        USER, "hi", source="test"
    )
    assert count == 0


# -- use cases --------------------------------------------------------------


async def test_connect_verifies_and_stores_label() -> None:
    repo = _FakeRepo()
    sender = _FakeSender(username="@mybot")
    view = await ConnectTelegram(
        repository=repo, senders={Channel.TELEGRAM: sender}, clock=FixedClock(NOW)
    )(ConnectTelegramCommand(user_id=USER, tenant_id=TENANT, bot_token=_TOKEN))
    assert view.label == "@mybot"
    assert view.configured is True
    assert view.verified is False  # no chat yet


async def test_detect_chat_links_target() -> None:
    repo = _FakeRepo()
    sender = _FakeSender(target="999")
    clock = FixedClock(NOW)
    await ConnectTelegram(repository=repo, senders={Channel.TELEGRAM: sender}, clock=clock)(
        ConnectTelegramCommand(user_id=USER, tenant_id=TENANT, bot_token=_TOKEN)
    )
    view = await DetectTelegramChat(
        repository=repo, senders={Channel.TELEGRAM: sender}, clock=clock
    )(DetectTelegramChatCommand(user_id=USER))
    assert view.target == "999"
    assert view.verified is True
    assert view.ready is True


async def test_detect_chat_raises_when_none_found() -> None:
    repo = _FakeRepo()
    sender = _FakeSender(target=None)
    clock = FixedClock(NOW)
    await ConnectTelegram(repository=repo, senders={Channel.TELEGRAM: sender}, clock=clock)(
        ConnectTelegramCommand(user_id=USER, tenant_id=TENANT, bot_token=_TOKEN)
    )
    with pytest.raises(ChannelVerificationError):
        await DetectTelegramChat(repository=repo, senders={Channel.TELEGRAM: sender}, clock=clock)(
            DetectTelegramChatCommand(user_id=USER)
        )


async def test_send_test_requires_a_linked_chat() -> None:
    repo = _FakeRepo()
    sender = _FakeSender()
    clock = FixedClock(NOW)
    await ConnectTelegram(repository=repo, senders={Channel.TELEGRAM: sender}, clock=clock)(
        ConnectTelegramCommand(user_id=USER, tenant_id=TENANT, bot_token=_TOKEN)
    )
    with pytest.raises(ChannelVerificationError):
        await SendTestMessage(repository=repo, senders={Channel.TELEGRAM: sender})(
            USER, Channel.TELEGRAM
        )
