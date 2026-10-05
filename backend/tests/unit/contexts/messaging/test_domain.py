"""Messaging domain — the channel aggregate lifecycle and credentials VO."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from chartnexus.contexts.messaging.domain.channel import Channel, ChannelConnection
from chartnexus.contexts.messaging.domain.credentials import TelegramCredentials
from chartnexus.contexts.messaging.domain.errors import ChannelCredentialsInvalidError
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId

NOW = datetime(2026, 8, 23, tzinfo=UTC)
USER = UserId(uuid.uuid4())
TENANT = TenantId(uuid.uuid4())
_VALID_TOKEN = "123456789:AAqwertyuiopasdfghjklzxcvbnm12345678"


def _connection() -> ChannelConnection:
    return ChannelConnection.create(
        user_id=USER,
        tenant_id=TENANT,
        channel=Channel.TELEGRAM,
        secret=_VALID_TOKEN,
        label="@mybot",
        now=NOW,
    )


def test_credentials_parse_valid_token() -> None:
    creds = TelegramCredentials.parse(f"  {_VALID_TOKEN}  ")
    assert creds.bot_token == _VALID_TOKEN
    assert creds.chat_id is None


def test_credentials_reject_non_token() -> None:
    with pytest.raises(ChannelCredentialsInvalidError):
        TelegramCredentials.parse("not-a-token")


def test_credentials_repr_hides_token() -> None:
    assert _VALID_TOKEN not in repr(TelegramCredentials.parse(_VALID_TOKEN))


def test_new_connection_is_configured_but_not_ready() -> None:
    conn = _connection()
    assert conn.configured is True
    assert conn.verified is False
    assert conn.ready is False  # no target yet


def test_linking_target_makes_it_ready() -> None:
    conn = _connection()
    conn.link_target("987654321", NOW)
    assert conn.target == "987654321"
    assert conn.verified is True
    assert conn.ready is True


def test_updating_token_drops_the_target() -> None:
    conn = _connection()
    conn.link_target("987654321", NOW)
    conn.update_credentials(
        secret="111:BBnewnewnewnewnewnewnewnewnewnew12", label="@renamed", now=NOW
    )
    assert conn.target is None
    assert conn.verified is False
    assert conn.ready is False


def test_disabling_a_ready_connection_makes_it_not_ready() -> None:
    conn = _connection()
    conn.link_target("987654321", NOW)
    conn.set_enabled(False, NOW)
    assert conn.enabled is False
    assert conn.ready is False


def test_masked_secret_hides_the_token() -> None:
    conn = _connection()
    masked = conn.masked_secret
    assert masked is not None
    assert _VALID_TOKEN not in masked
