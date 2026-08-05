"""``RedisIvHistoryRecorder`` against real Redis.

Requires the compose stack:  docker compose -f deploy/compose/compose.yml up -d
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest

from marketcompass.bootstrap.settings import RedisSettings
from marketcompass.infrastructure.cache.redis.client import RedisClient
from marketcompass.infrastructure.cache.redis.iv_history import RedisIvHistoryRecorder

pytestmark = pytest.mark.integration

TODAY = date(2026, 8, 5)


@pytest.fixture
async def redis() -> AsyncIterator[RedisClient]:
    client = RedisClient.create(
        RedisSettings(url="redis://localhost:6381/0", key_prefix=f"it-iv-{uuid.uuid4().hex[:8]}")
    )
    try:
        yield client
    finally:
        await client.close()


async def test_a_single_reading_ranks_at_the_top(redis: RedisClient) -> None:
    recorder = RedisIvHistoryRecorder(redis)

    rank = await recorder.record_and_rank(
        symbol="NIFTY", session_date=TODAY, atm_iv=Decimal("12.5")
    )

    assert rank == Decimal("100.0")


async def test_rank_reflects_where_todays_reading_sits_among_earlier_ones(
    redis: RedisClient,
) -> None:
    recorder = RedisIvHistoryRecorder(redis)

    for value in ("10.0", "12.0", "14.0", "16.0"):
        await recorder.record_and_rank(symbol="NIFTY", session_date=TODAY, atm_iv=Decimal(value))
    # A 5th reading lower than every prior one ranks at the bottom of the five.
    rank = await recorder.record_and_rank(symbol="NIFTY", session_date=TODAY, atm_iv=Decimal("5.0"))

    assert rank == Decimal("20.0")


async def test_symbols_and_sessions_do_not_share_history(redis: RedisClient) -> None:
    recorder = RedisIvHistoryRecorder(redis)

    await recorder.record_and_rank(symbol="NIFTY", session_date=TODAY, atm_iv=Decimal("50.0"))
    # A different symbol, and a different day, must each start from a clean slate.
    other_symbol_rank = await recorder.record_and_rank(
        symbol="BANKNIFTY", session_date=TODAY, atm_iv=Decimal("1.0")
    )
    other_day_rank = await recorder.record_and_rank(
        symbol="NIFTY", session_date=date(2026, 8, 6), atm_iv=Decimal("1.0")
    )

    assert other_symbol_rank == Decimal("100.0")
    assert other_day_rank == Decimal("100.0")
