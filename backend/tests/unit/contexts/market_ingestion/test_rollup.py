"""Rolling the intraday archive up into one IV reading per session.

This use case is the only thing standing between the system and permanently
losing its volatility history, so the cases worth pinning are the ones where it
would quietly write nothing, or write the wrong day.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from chartnexus.contexts.market_ingestion.application.rollup import (
    RollupDailyIv,
    SessionIv,
)

_IST = timezone(timedelta(hours=5, minutes=30))
# 20:00 UTC on 2 Sep is 01:30 IST on 3 Sep — the window where a UTC-derived
# date is a day behind the trading date.
LATE_EVENING = datetime(2026, 9, 2, 20, 0, tzinfo=UTC)
MIDDAY = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)


def _iv(symbol: str, day: int) -> SessionIv:
    return SessionIv(
        symbol=symbol,
        session_date=date(2026, 9, day),
        atm_iv=Decimal("12.5"),
        future_close=Decimal("24650.00"),
        captures=100,
        source="mock",
    )


class StubSource:
    def __init__(self, per_symbol: dict[str, list[SessionIv]]) -> None:
        self._per_symbol = per_symbol
        self.asked: list[tuple[str, date]] = []

    async def session_ivs(self, symbol: str, *, since: date) -> list[SessionIv]:
        self.asked.append((symbol, since))
        return list(self._per_symbol.get(symbol, []))


class StubWriter:
    def __init__(self) -> None:
        self.written: list[SessionIv] = []

    async def upsert_daily_iv(self, rows: list[SessionIv]) -> int:
        self.written.extend(rows)
        return len(rows)


class StubClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def _use_case(
    per_symbol: dict[str, list[SessionIv]], *, now: datetime = MIDDAY
) -> tuple[RollupDailyIv, StubSource, StubWriter]:
    source = StubSource(per_symbol)
    writer = StubWriter()
    return RollupDailyIv(source=source, writer=writer, clock=StubClock(now)), source, writer


@pytest.mark.asyncio
async def test_writes_every_archived_session_for_every_symbol() -> None:
    """It backfills the window, rather than only yesterday.

    That is what turns an existing 30-day archive into 30 days of durable IV the
    first time it runs, instead of one day.
    """
    use_case, _, writer = _use_case(
        {"NIFTY": [_iv("NIFTY", 1), _iv("NIFTY", 2)], "SENSEX": [_iv("SENSEX", 2)]}
    )

    result = await use_case(["NIFTY", "SENSEX"], lookback_days=30)

    assert result.written == 3
    assert {(row.symbol, row.session_date) for row in writer.written} == {
        ("NIFTY", date(2026, 9, 1)),
        ("NIFTY", date(2026, 9, 2)),
        ("SENSEX", date(2026, 9, 2)),
    }


@pytest.mark.asyncio
async def test_a_symbol_with_nothing_archived_is_skipped_not_written() -> None:
    use_case, _, writer = _use_case({"NIFTY": [_iv("NIFTY", 1)], "SENSEX": []})

    result = await use_case(["NIFTY", "SENSEX"], lookback_days=30)

    assert result.written == 1
    assert result.skipped == 1
    assert all(row.symbol == "NIFTY" for row in writer.written)


@pytest.mark.asyncio
async def test_the_lookback_is_measured_from_the_ist_trading_date() -> None:
    """Late on a UTC evening it is already tomorrow in IST.

    Deriving the bound from the UTC date would ask for one day less than the
    retention window and silently drop the oldest session — the very one about
    to be pruned.
    """
    use_case, source, _ = _use_case({"NIFTY": []}, now=LATE_EVENING)

    await use_case(["NIFTY"], lookback_days=30)

    _symbol, since = source.asked[0]
    assert since == date(2026, 9, 3) - timedelta(days=30)


@pytest.mark.asyncio
async def test_a_zero_lookback_still_asks_for_at_least_a_day() -> None:
    """A window of zero would resolve to "since today" and quietly archive nothing."""
    use_case, source, _ = _use_case({"NIFTY": []})

    await use_case(["NIFTY"], lookback_days=0)

    _symbol, since = source.asked[0]
    assert since < MIDDAY.astimezone(_IST).date()


@pytest.mark.asyncio
async def test_no_symbols_is_a_no_op_rather_than_an_error() -> None:
    use_case, _, writer = _use_case({})

    result = await use_case([], lookback_days=30)

    assert result == type(result)(written=0, skipped=0)
    assert writer.written == []
