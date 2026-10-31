"""Connecting the alert bot, and proving the connection actually delivers.

The property these exist for: linking a chat must not be an act of faith. A
chat id the bot cannot post to looks identical to a working one in the
database, and the difference only shows up when a real break goes missing —
so the link is proven by delivering to it, at the moment it is made.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from chartnexus.contexts.trade_buddy.api.schemas import LinkChatRequest
from chartnexus.contexts.trade_buddy.application.channels import (
    WELCOME_MESSAGE,
    ConnectChannel,
    ConnectCommand,
    DisconnectChannel,
    GetChannels,
    LinkChat,
    SendChannelTest,
    SetChannelEnabled,
)
from chartnexus.contexts.trade_buddy.application.ports import ChannelIdentity
from chartnexus.contexts.trade_buddy.domain.channel import (
    AlertChannel,
    AlertConnection,
    is_valid_chat_id,
)
from chartnexus.contexts.trade_buddy.domain.errors import (
    ChannelNotReadyError,
    ChannelVerificationError,
)
from chartnexus.infrastructure.trade_buddy.clock import FakeClock
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
USER = UserId(uuid.uuid4())
TENANT = TenantId(uuid.uuid4())


@dataclass
class MemoryChannels:
    rows: dict[tuple[UserId, AlertChannel], AlertConnection] = field(default_factory=dict)

    async def find(self, user_id, channel):  # type: ignore[no-untyped-def]
        return self.rows.get((user_id, channel))

    async def find_all(self, user_id):  # type: ignore[no-untyped-def]
        return tuple(v for (u, _), v in self.rows.items() if u == user_id)

    async def find_any_ready(self, channel):  # type: ignore[no-untyped-def]
        return next((v for (_, c), v in self.rows.items() if c == channel and v.ready), None)

    async def upsert(self, connection):  # type: ignore[no-untyped-def]
        self.rows[(connection.user_id, connection.channel)] = connection

    async def delete(self, user_id, channel):  # type: ignore[no-untyped-def]
        self.rows.pop((user_id, channel), None)


@dataclass
class FakeSender:
    """Records what was sent, and can be told to fail at any step."""

    username: str = "@alerts_bot"
    detected: str | None = "999"
    sent: list[tuple[str, str]] = field(default_factory=list)
    verify_fails: bool = False
    send_fails: bool = False

    async def verify(self, secret: str) -> ChannelIdentity:
        if self.verify_fails:
            raise ChannelVerificationError("bad token", provider="telegram")
        return ChannelIdentity(label=self.username)

    async def detect_target(self, secret: str) -> str | None:
        return self.detected

    async def send(self, secret: str, target: str, text: str) -> None:
        if self.send_fails:
            raise RuntimeError("chat not found")
        self.sent.append((target, text))


def build(sender: FakeSender | None = None):  # type: ignore[no-untyped-def]
    repo = MemoryChannels()
    snd = sender or FakeSender()
    clock = FakeClock(NOW)
    return repo, snd, clock


async def connected(repo, snd, clock) -> AlertConnection:  # type: ignore[no-untyped-def]
    return await ConnectChannel(repository=repo, sender=snd, clock=clock)(
        ConnectCommand(
            user_id=USER, tenant_id=TENANT, channel=AlertChannel.TELEGRAM, secret="tok123456"
        )
    )


class TestConnecting:
    async def test_a_verified_token_is_stored_with_the_bot_name(self):
        repo, snd, clock = build()
        connection = await connected(repo, snd, clock)

        assert connection.configured
        assert connection.label == "@alerts_bot"
        # Not ready yet: a token without a chat cannot deliver anywhere.
        assert not connection.ready

    async def test_a_refused_token_is_never_stored(self):
        """A connection the provider has already rejected must not appear in
        the panel as though it might work."""
        repo, snd, clock = build(FakeSender(verify_fails=True))

        with pytest.raises(ChannelVerificationError):
            await connected(repo, snd, clock)
        assert repo.rows == {}

    async def test_replacing_the_token_drops_the_linked_chat(self):
        repo, snd, clock = build()
        await connected(repo, snd, clock)
        await LinkChat(repository=repo, sender=snd, clock=clock)(USER, AlertChannel.TELEGRAM)
        assert repo.rows[(USER, AlertChannel.TELEGRAM)].ready

        # A new token may be a different bot, and the old chat id would point
        # at a conversation the new bot is not in.
        await ConnectChannel(repository=repo, sender=snd, clock=clock)(
            ConnectCommand(
                user_id=USER,
                tenant_id=TENANT,
                channel=AlertChannel.TELEGRAM,
                secret="different99",
            )
        )
        reloaded = repo.rows[(USER, AlertChannel.TELEGRAM)]
        assert reloaded.target is None
        assert not reloaded.verified


class TestLinkingSendsAWelcome:
    async def test_linking_delivers_a_welcome_message(self):
        repo, snd, clock = build()
        await connected(repo, snd, clock)

        await LinkChat(repository=repo, sender=snd, clock=clock)(USER, AlertChannel.TELEGRAM)

        assert len(snd.sent) == 1
        target, text = snd.sent[0]
        assert target == "999"
        assert text == WELCOME_MESSAGE

    async def test_the_welcome_says_what_will_arrive_and_when(self):
        # The next message from this bot may be days later and mid-trade. It
        # should be expected, not a surprise from a forgotten sender.
        assert "Trade Buddy" in WELCOME_MESSAGE
        assert "09:15" in WELCOME_MESSAGE
        assert "15:20" in WELCOME_MESSAGE

    async def test_a_chat_that_cannot_receive_is_not_linked(self):
        """The whole point of sending before storing.

        A chat id the bot cannot post to is indistinguishable from a good one
        in the database. Storing it would show "Ready" for a channel that
        silently drops every alert.
        """
        repo, snd, clock = build(FakeSender(send_fails=True))
        await connected(repo, snd, clock)

        with pytest.raises(ChannelVerificationError, match="could not deliver"):
            await LinkChat(repository=repo, sender=snd, clock=clock)(USER, AlertChannel.TELEGRAM)

        stored = repo.rows[(USER, AlertChannel.TELEGRAM)]
        assert stored.target is None
        assert not stored.ready

    async def test_a_manual_chat_id_is_proven_the_same_way(self):
        repo, snd, clock = build(FakeSender(detected=None))
        await connected(repo, snd, clock)

        await LinkChat(repository=repo, sender=snd, clock=clock)(
            USER, AlertChannel.TELEGRAM, target="  4242  "
        )

        assert snd.sent[0][0] == "4242"
        assert repo.rows[(USER, AlertChannel.TELEGRAM)].target == "4242"

    async def test_nobody_having_messaged_the_bot_is_not_an_error(self):
        """A bot cannot open a conversation, so this is a normal first run.
        Nothing is sent and nothing is stored."""
        repo, snd, clock = build(FakeSender(detected=None))
        await connected(repo, snd, clock)

        connection = await LinkChat(repository=repo, sender=snd, clock=clock)(
            USER, AlertChannel.TELEGRAM
        )

        assert connection.target is None
        assert snd.sent == []

    async def test_linking_before_a_token_exists_is_refused(self):
        repo, snd, clock = build()
        with pytest.raises(ChannelNotReadyError):
            await LinkChat(repository=repo, sender=snd, clock=clock)(USER, AlertChannel.TELEGRAM)


class TestReadyState:
    async def test_a_linked_channel_is_ready(self):
        repo, snd, clock = build()
        await connected(repo, snd, clock)
        connection = await LinkChat(repository=repo, sender=snd, clock=clock)(
            USER, AlertChannel.TELEGRAM
        )
        assert connection.ready

    async def test_pausing_keeps_the_setup_but_stops_delivery(self):
        repo, snd, clock = build()
        await connected(repo, snd, clock)
        await LinkChat(repository=repo, sender=snd, clock=clock)(USER, AlertChannel.TELEGRAM)

        paused = await SetChannelEnabled(repository=repo, clock=clock)(
            USER, AlertChannel.TELEGRAM, enabled=False
        )

        assert not paused.ready
        # The token and the chat survive, so resuming is not a reconnect.
        assert paused.configured
        assert paused.target == "999"

    async def test_a_paused_channel_is_not_picked_up_by_the_watcher(self):
        repo, snd, clock = build()
        await connected(repo, snd, clock)
        await LinkChat(repository=repo, sender=snd, clock=clock)(USER, AlertChannel.TELEGRAM)
        await SetChannelEnabled(repository=repo, clock=clock)(
            USER, AlertChannel.TELEGRAM, enabled=False
        )

        assert await repo.find_any_ready(AlertChannel.TELEGRAM) is None

    async def test_disconnecting_forgets_everything(self):
        repo, snd, clock = build()
        await connected(repo, snd, clock)
        await DisconnectChannel(repository=repo)(USER, AlertChannel.TELEGRAM)

        assert await GetChannels(repository=repo)(USER) == ()


class TestManualTest:
    async def test_it_sends_once_ready(self):
        repo, snd, clock = build()
        await connected(repo, snd, clock)
        await LinkChat(repository=repo, sender=snd, clock=clock)(USER, AlertChannel.TELEGRAM)
        snd.sent.clear()

        await SendChannelTest(repository=repo, sender=snd)(USER, AlertChannel.TELEGRAM)

        assert len(snd.sent) == 1

    async def test_it_refuses_when_the_channel_cannot_deliver(self):
        repo, snd, clock = build()
        await connected(repo, snd, clock)  # token only, no chat

        with pytest.raises(ChannelNotReadyError):
            await SendChannelTest(repository=repo, sender=snd)(USER, AlertChannel.TELEGRAM)


class TestSecretHandling:
    async def test_the_token_is_masked_for_display(self):
        repo, snd, clock = build()
        connection = await connected(repo, snd, clock)

        masked = connection.masked_secret
        assert masked is not None
        assert connection.secret not in masked
        assert masked.startswith("tok1")
        assert masked.endswith("3456")

    async def test_a_short_secret_is_masked_entirely(self):
        connection = AlertConnection.create(
            user_id=USER,
            tenant_id=TENANT,
            channel=AlertChannel.TELEGRAM,
            secret="abc",
            label=None,
            now=NOW,
        )
        assert connection.masked_secret == "***"


class TestChatIdValidation:
    """A chat id that cannot be delivered to must never be stored.

    Regression: the word "Welcome" was typed into the chat-id box, accepted
    verbatim, and the channel then read as Ready. The failure only surfaced
    later as Telegram's "Bad Request: chat not found" — long after the typo,
    and on a channel the panel had been calling healthy.
    """

    @pytest.mark.parametrize("value", ["123456789", "-1001234567890", "@my_channel", "  42  "])
    def test_real_chat_ids_are_accepted(self, value):
        assert is_valid_chat_id(value)

    @pytest.mark.parametrize(
        "value", ["Welcome", "", "   ", "abc123", "12 34", "hello world", "@x", "@1channel"]
    )
    def test_anything_else_is_refused(self, value):
        assert not is_valid_chat_id(value)

    def test_the_request_schema_rejects_a_word_with_a_message_that_helps(self):
        with pytest.raises(PydanticValidationError, match="not a chat id"):
            LinkChatRequest(target="Welcome")

    def test_a_blank_target_still_means_auto_detect(self):
        assert LinkChatRequest(target=None).target is None
        assert LinkChatRequest(target="   ").target is None

    def test_a_valid_target_is_trimmed(self):
        assert LinkChatRequest(target="  987654  ").target == "987654"
