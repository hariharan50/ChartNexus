"""When the previous-session OI baseline is captured.

Kite publishes no previous-day OI, so every OI change under Kite depends on a
capture taken before 09:15. Kite tokens expire at 06:00, so the 08:35 morning
sync often finds no connection; the capture must also run when the user
reconnects before the open, or the whole day reads an OI change of zero.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from chartnexus.infrastructure.brokers.kite import sync

# 08:46 and 09:16 IST on 19 Nov 2026.
BEFORE_OPEN = datetime(2026, 11, 19, 3, 16, tzinfo=UTC)
AFTER_OPEN = datetime(2026, 11, 19, 3, 46, tzinfo=UTC)


class _Clock(datetime):
    at: datetime = BEFORE_OPEN

    @classmethod
    def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
        return cls.at.astimezone(tz) if tz else cls.at


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(captured=[], catalog_result=42, connection=None)
    state.connection = SimpleNamespace(is_connected=True, broker=sync.BrokerName.KITE)

    class _Repository:
        def __init__(self, *_: Any) -> None: ...

        async def find(self, *_: Any) -> Any:
            return state.connection

        async def find_market_feed(self) -> Any:
            return state.connection

    @asynccontextmanager
    async def read_session() -> Any:
        yield object()

    async def fake_sync(_container: Any, _connection: Any) -> int | None:
        return state.catalog_result

    async def fake_capture(_container: Any, connection: Any) -> None:
        state.captured.append(connection)

    monkeypatch.setattr(sync, "SqlAlchemyBrokerConnectionRepository", _Repository)
    monkeypatch.setattr(sync, "sync_for_connection", fake_sync)
    monkeypatch.setattr(sync, "capture_previous_oi", fake_capture)
    monkeypatch.setattr(sync, "datetime", _Clock)
    state.container = SimpleNamespace(
        database=SimpleNamespace(read_session=read_session), token_cipher=None
    )
    return state


class TestReconnectBeforeTheOpen:
    async def test_captures_the_baseline(self, harness: SimpleNamespace) -> None:
        _Clock.at = BEFORE_OPEN
        await sync.sync_after_connect(harness.container, tenant_id="t")
        assert harness.captured == [harness.connection]

    async def test_skips_it_once_the_market_is_open(self, harness: SimpleNamespace) -> None:
        """After 09:15 Kite's ``oi`` is today's, so storing it would be wrong."""
        _Clock.at = AFTER_OPEN
        await sync.sync_after_connect(harness.container, tenant_id="t")
        assert harness.captured == []

    async def test_skips_it_when_the_catalog_sync_failed(self, harness: SimpleNamespace) -> None:
        _Clock.at = BEFORE_OPEN
        harness.catalog_result = None
        await sync.sync_after_connect(harness.container, tenant_id="t")
        assert harness.captured == []

    async def test_does_nothing_without_a_live_connection(self, harness: SimpleNamespace) -> None:
        _Clock.at = BEFORE_OPEN
        harness.connection.is_connected = False
        await sync.sync_after_connect(harness.container, tenant_id="t")
        assert harness.captured == []


class TestMorningSync:
    async def test_still_captures_before_the_open(self, harness: SimpleNamespace) -> None:
        _Clock.at = BEFORE_OPEN
        await sync.morning_sync(harness.container)
        assert harness.captured == [harness.connection]

    async def test_still_skips_after_the_open(self, harness: SimpleNamespace) -> None:
        _Clock.at = AFTER_OPEN
        await sync.morning_sync(harness.container)
        assert harness.captured == []
