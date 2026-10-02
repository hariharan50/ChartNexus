"""The rolling at-the-money straddle behind the Straddle Chart tool.

The cases pinned here are the ones that would draw a confident wrong chart: a
strike that stops following the money (which turns "the cost of being at the
money" into the price of one stale contract), a straddle drawn from a single
quoted leg (which reads as a collapse in premium rather than as a missing
quote), and a multi-session window counted on the calendar instead of in
sessions (which quietly returns a day and a half over a long weekend).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from marketcompass.contexts.options_analytics.application.ports import (
    ChainSnapshot,
    ProviderChain,
)
from marketcompass.contexts.options_analytics.application.straddle_chart_service import (
    MAX_SESSIONS,
    GetStraddleChart,
)
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow
from marketcompass.shared_kernel.types.identifiers import TenantId

pytestmark = pytest.mark.unit

TENANT = TenantId(uuid.uuid4())
# 08:00 UTC == 13:30 IST, inside the session on 2026-10-01.
NOW = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
#: 09:15 IST, the session bell, in UTC.
OPEN = datetime(2026, 10, 1, 3, 45, tzinfo=UTC)
EXPIRY = "2026-10-06"
SPOT = 22_400.0
LOT = 75


def _row(side: str, strike: float, *, ltp: float) -> ChainRow:
    return ChainRow(
        strike=strike, option_type=side, oi=1_000, oi_change=0, ltp=ltp, volume=1, iv=14.0
    )


def _ladder(
    *, call: dict[float, float] | None = None, put: dict[float, float] | None = None
) -> tuple[ChainRow, ...]:
    """Five strikes either side of 22400, at 50-point spacing."""
    calls = call or {}
    puts = put or {}
    rows: list[ChainRow] = []
    for offset in range(-5, 6):
        strike = SPOT + 50.0 * offset
        rows.append(_row("CE", strike, ltp=calls.get(strike, 160.45)))
        rows.append(_row("PE", strike, ltp=puts.get(strike, 95.65)))
    return tuple(rows)


def _snap(
    minute: int,
    rows: tuple[ChainRow, ...] | None = None,
    *,
    atm: float | None = SPOT,
    spot: float | None = SPOT,
    day: int = 0,
) -> ChainSnapshot:
    return ChainSnapshot(
        captured_at=OPEN + timedelta(days=day, minutes=minute),
        rows=rows if rows is not None else _ladder(),
        expiry=EXPIRY,
        spot=spot,
        atm_strike=atm,
        future_price=(spot or SPOT) + 40.0,
    )


class StubProvider:
    def __init__(self, expiry: str | None = EXPIRY, rows: tuple[ChainRow, ...] = ()) -> None:
        self._expiry = expiry
        self._rows = rows

    async def fetch(
        self, tenant_id: TenantId, symbol: str, *, expiry: str | None = None
    ) -> ProviderChain:
        return ProviderChain(rows=self._rows, spot=SPOT, lot_size=LOT, expiry=self._expiry)


class StubReader:
    """Records what the service asked for as well as answering it."""

    def __init__(self, day: list[ChainSnapshot], window: list[ChainSnapshot] | None = None) -> None:
        self._day = day
        self._window = window if window is not None else day
        self.asked_sessions: int | None = None

    async def latest_in_session(self, tenant_id, symbol, *, now_utc):  # type: ignore[no-untyped-def]
        return self._day[-1] if self._day else None

    async def day_snapshots(self, tenant_id, symbol, *, trade_date_utc):  # type: ignore[no-untyped-def]
        return list(self._day)

    async def recent_session_snapshots(self, tenant_id, symbol, *, end_utc, sessions):  # type: ignore[no-untyped-def]
        self.asked_sessions = sessions
        return list(self._window)


def _service(reader: StubReader, *, chain_rows: tuple[ChainRow, ...] = ()) -> GetStraddleChart:
    return GetStraddleChart(
        provider=StubProvider(EXPIRY, chain_rows),
        snapshots=reader,
        now_utc=lambda: NOW,
    )


# -- the rolling strike ------------------------------------------------------


@pytest.mark.asyncio
async def test_each_capture_is_priced_at_its_own_at_the_money_strike() -> None:
    """The subject is the cost of being at the money, not one contract's price."""
    reader = StubReader([_snap(0, atm=SPOT), _snap(60, atm=SPOT + 100.0, spot=SPOT + 100.0)])

    payload = await _service(reader)(TENANT, "NIFTY")

    assert payload["series"]["strike"] == [SPOT, SPOT + 100.0]
    assert payload["rolling_strike"] is True
    # The header names the contract in force now, which is the later one.
    assert payload["atm_strike"] == SPOT + 100.0


@pytest.mark.asyncio
async def test_the_straddle_is_the_two_legs_at_that_strike() -> None:
    reader = StubReader([_snap(0, _ladder(call={SPOT: 160.45}, put={SPOT: 95.65}))])

    payload = await _service(reader)(TENANT, "NIFTY")

    assert payload["series"]["ce"] == [160.45]
    assert payload["series"]["pe"] == [95.65]
    assert payload["straddle_price"] == pytest.approx(256.10)


@pytest.mark.asyncio
async def test_a_capture_with_one_unquoted_leg_is_dropped_not_halved() -> None:
    """A straddle missing a leg is unknown, not cheap — half of it is a lie."""
    reader = StubReader([_snap(0, _ladder(put={SPOT: 0.0})), _snap(30)])

    payload = await _service(reader)(TENANT, "NIFTY")

    assert len(payload["series"]["t"]) == 1
    assert payload["series"]["straddle"] == [256.10]


@pytest.mark.asyncio
async def test_the_strike_is_derived_when_a_capture_carries_no_atm() -> None:
    """Older rows predate the denormalised header; the ladder still has one."""
    reader = StubReader([_snap(0, atm=None, spot=SPOT + 20.0)])

    payload = await _service(reader)(TENANT, "NIFTY")

    # The future (spot + 40) is what the ATM is taken against, so 22450 wins.
    assert payload["series"]["strike"] == [SPOT + 50.0]


# -- the other two lines -----------------------------------------------------


@pytest.mark.asyncio
async def test_the_synthetic_forward_comes_from_parity_at_the_money() -> None:
    """`call - put + strike`: the forward the options themselves imply."""
    reader = StubReader([_snap(0, _ladder(call={SPOT: 180.3}, put={SPOT: 131.6}))])

    payload = await _service(reader)(TENANT, "NIFTY")

    assert payload["synthetic_future"] == pytest.approx(SPOT + 180.3 - 131.6)
    assert payload["spot"] == SPOT


@pytest.mark.asyncio
async def test_the_forward_falls_back_to_the_future_when_parity_cannot_be_taken() -> None:
    """A hole in the forward line is worse than the tradable future in its place.

    The call is quoted and the put is not, so the straddle itself is unknown and
    this capture is dropped — but the *fallback* has to be there for the frames
    that survive, which is what the second capture checks.
    """
    reader = StubReader([_snap(0, _ladder(call={SPOT: 0.0}, put={SPOT: 0.0})), _snap(30)])

    payload = await _service(reader)(TENANT, "NIFTY")

    assert payload["synthetic_future"] is not None


# -- the window --------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_multi_day_range_is_counted_in_sessions() -> None:
    """Three days means three sessions, not three squares on a calendar."""
    reader = StubReader([], window=[_snap(0, day=-4), _snap(0, day=-1), _snap(0)])

    payload = await _service(reader)(TENANT, "NIFTY", sessions=3)

    assert reader.asked_sessions == 3
    assert payload["covered_sessions"] == 3
    assert payload["requested_sessions"] == 3
    assert len(payload["series"]["t"]) == 3


@pytest.mark.asyncio
async def test_one_session_reads_the_day_rather_than_the_window() -> None:
    reader = StubReader([_snap(0), _snap(30)])

    payload = await _service(reader)(TENANT, "NIFTY", sessions=1)

    assert reader.asked_sessions is None
    assert payload["covered_sessions"] == 1


@pytest.mark.asyncio
async def test_an_oversized_request_is_clamped_to_what_the_archive_holds() -> None:
    reader = StubReader([], window=[_snap(0)])

    payload = await _service(reader)(TENANT, "NIFTY", sessions=999)

    assert reader.asked_sessions == MAX_SESSIONS
    assert payload["requested_sessions"] == MAX_SESSIONS


# -- degradation -------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_day_with_no_archive_falls_back_to_one_live_point() -> None:
    payload = await _service(StubReader([]), chain_rows=_ladder())(TENANT, "NIFTY")

    assert payload["data_quality"] == "live"
    assert len(payload["series"]["t"]) == 1
    assert payload["straddle_price"] == 256.10


@pytest.mark.asyncio
async def test_nothing_at_all_is_an_empty_payload_not_a_crash() -> None:
    payload = await _service(StubReader([]))(TENANT, "NIFTY")

    assert payload["data_quality"] == "empty"
    assert payload["straddle_price"] is None
    assert payload["series"]["t"] == []


@pytest.mark.asyncio
async def test_an_archive_of_another_expiry_is_not_drawn_under_this_header() -> None:
    other = ChainSnapshot(
        captured_at=OPEN + timedelta(minutes=10),
        rows=_ladder(),
        expiry="2026-10-27",
        spot=SPOT,
        atm_strike=SPOT,
    )

    payload = await _service(StubReader([other]), chain_rows=_ladder())(TENANT, "NIFTY")

    # Dropped to the live tier rather than relabelling the far contract's rows.
    assert payload["data_quality"] == "live"
