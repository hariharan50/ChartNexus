"""Daily implied-volatility history behind the IV/HV/IVP Chart.

The service does almost nothing on purpose — the point of the tests is the two
places where "almost nothing" could still mislead: the IST date bound, and the
coverage count that stops a fortnight of history being read as a year of it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from chartnexus.contexts.options_analytics.application.iv_history_service import GetIvHistory
from chartnexus.contexts.options_analytics.application.ports import DailyIv
from chartnexus.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())
# 20:00 UTC on 2 Sep is 01:30 IST on 3 Sep — the window where a UTC-derived
# date is a day behind the trading date.
LATE_EVENING = datetime(2026, 9, 2, 20, 0, tzinfo=UTC)
MIDDAY = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)


class StubReader:
    def __init__(self, readings: list[DailyIv]) -> None:
        self.readings = readings
        self.calls: list[tuple[str, date, date]] = []

    async def daily_iv(self, tenant_id, symbol, *, start, end):  # type: ignore[no-untyped-def]
        self.calls.append((symbol, start, end))
        return [r for r in self.readings if start <= r.session_date <= end]


def _reading(day: int, iv: float = 12.0, captures: int = 100) -> DailyIv:
    return DailyIv(
        session_date=date(2026, 9, day),
        atm_iv=iv,
        future_close=24_650.0,
        captures=captures,
    )


def _service(readings: list[DailyIv], *, now: datetime = MIDDAY) -> tuple[GetIvHistory, StubReader]:
    reader = StubReader(readings)
    return GetIvHistory(readings=reader, now_utc=lambda: now), reader


@pytest.mark.asyncio
async def test_hands_the_stored_sessions_over_oldest_first() -> None:
    service, _ = _service([_reading(1, 11.5), _reading(2, 12.25)])

    payload = await service(TENANT, "NIFTY", days=365)

    assert [session["d"] for session in payload["sessions"]] == ["2026-09-01", "2026-09-02"]
    assert [session["iv"] for session in payload["sessions"]] == [11.5, 12.25]
    assert payload["symbol"] == "NIFTY"


@pytest.mark.asyncio
async def test_reports_how_much_history_actually_exists() -> None:
    """A year asked for and a fortnight returned must not look the same.

    IV Percentile over 10 sessions is a different claim from one over 250, and
    the page can only say so if the payload does.
    """
    service, _ = _service([_reading(1), _reading(2), _reading(3)])

    payload = await service(TENANT, "NIFTY", days=365)

    assert payload["requested_days"] == 365
    assert payload["covered_sessions"] == 3


@pytest.mark.asyncio
async def test_an_empty_archive_is_a_well_formed_payload_not_an_error() -> None:
    service, _ = _service([])

    payload = await service(TENANT, "NIFTY", days=90)

    assert payload["sessions"] == []
    assert payload["covered_sessions"] == 0
    assert payload["requested_days"] == 90


@pytest.mark.asyncio
async def test_the_window_is_bounded_by_the_ist_trading_date() -> None:
    """Late on a UTC evening it is already tomorrow in IST.

    `session_date` is an IST date, so a UTC-derived bound would drop the current
    session for five and a half hours every evening.
    """
    service, reader = _service([], now=LATE_EVENING)

    await service(TENANT, "NIFTY", days=7)

    _symbol, start, end = reader.calls[0]
    assert end == date(2026, 9, 3)
    assert start == date(2026, 8, 27)


@pytest.mark.asyncio
async def test_the_requested_window_is_clamped_to_something_servable() -> None:
    service, reader = _service([])

    assert (await service(TENANT, "NIFTY", days=9_999))["requested_days"] == 365
    assert (await service(TENANT, "NIFTY", days=0))["requested_days"] == 1

    # And the clamp reaches the reader, not just the header.
    _symbol, start, end = reader.calls[0]
    assert (end - start).days == 365


@pytest.mark.asyncio
async def test_carries_the_capture_count_and_the_future_close() -> None:
    """Both are what let the client weigh a reading rather than just plot it."""
    service, _ = _service([_reading(1, captures=2)])

    session = (await service(TENANT, "NIFTY", days=30))["sessions"][0]

    assert session["captures"] == 2
    assert session["future_close"] == 24_650.0
