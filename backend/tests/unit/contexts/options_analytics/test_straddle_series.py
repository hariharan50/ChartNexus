"""Per-strike straddle premiums behind the ATM Straddle Chart tool.

The cases pinned here are the ones that would draw a confident wrong chart: a
rolling ATM straddle that does not follow the money, an illiquid zero-priced leg
that halves a straddle, and a synthetic opening bar for a premium nobody printed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from marketcompass.contexts.options_analytics.application.ports import (
    ChainSnapshot,
    ProviderChain,
)
from marketcompass.contexts.options_analytics.application.straddle_series_service import (
    GetStraddleSeries,
)
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow
from marketcompass.contexts.options_analytics.domain.straddle_math import atm_straddle, leg_ltp
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())
# 08:00 UTC == 13:30 IST, inside the session on 2026-08-04.
NOW = datetime(2026, 8, 4, 8, 0, tzinfo=UTC)
EXPIRY = "2026-08-11"
SPOT = 24_650.0
LOT = 75


def _row(
    side: str, strike: float, *, ltp: float = 10.0, oi: int = 1_000, iv: float | None = 14.0
) -> ChainRow:
    return ChainRow(strike=strike, option_type=side, oi=oi, oi_change=0, ltp=ltp, volume=1, iv=iv)


def _ladder(*, call_ltp: dict[float, float] | None = None, put_ltp: dict[float, float] | None = None) -> tuple[ChainRow, ...]:
    """Five strikes either side of 24650, at 50-point spacing."""
    strikes = [SPOT + 50.0 * offset for offset in range(-5, 6)]
    calls = call_ltp or {}
    puts = put_ltp or {}
    rows: list[ChainRow] = []
    for strike in strikes:
        rows.append(_row("CE", strike, ltp=calls.get(strike, 100.0)))
        rows.append(_row("PE", strike, ltp=puts.get(strike, 90.0)))
    return tuple(rows)


#: 09:15 IST, the session bell, in UTC.
OPEN = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)


def _snap(
    minute: int,
    rows: tuple[ChainRow, ...],
    *,
    spot: float | None = SPOT,
    atm: float | None = SPOT,
) -> ChainSnapshot:
    return ChainSnapshot(
        captured_at=OPEN + timedelta(minutes=minute),
        rows=rows,
        spot=spot,
        atm_strike=atm,
        future_price=24_700.0,
    )


class StubProvider:
    def __init__(self, expiry: str | None = EXPIRY) -> None:
        self._expiry = expiry

    async def fetch(self, tenant_id: TenantId, symbol: str) -> ProviderChain:
        return ProviderChain(rows=(), spot=SPOT, lot_size=LOT, expiry=self._expiry)


class StubReader:
    def __init__(self, snapshots: list[ChainSnapshot]) -> None:
        self._snapshots = snapshots

    async def latest_in_session(self, tenant_id, symbol, *, now_utc):  # type: ignore[no-untyped-def]
        return self._snapshots[-1] if self._snapshots else None

    async def day_snapshots(self, tenant_id, symbol, *, trade_date_utc):  # type: ignore[no-untyped-def]
        return list(self._snapshots)


def _service(snapshots: list[ChainSnapshot], *, expiry: str | None = EXPIRY) -> GetStraddleSeries:
    return GetStraddleSeries(
        provider=StubProvider(expiry),
        snapshots=StubReader(snapshots),
        now_utc=lambda: NOW,
    )


# -- the straddle math ------------------------------------------------------


def test_atm_straddle_is_call_plus_put_at_the_money() -> None:
    rows = (_row("CE", SPOT, ltp=120.0), _row("PE", SPOT, ltp=70.0))

    assert atm_straddle(rows, SPOT) == 190.0


def test_atm_straddle_needs_both_legs_and_ignores_a_zero_print() -> None:
    only_call = (_row("CE", SPOT, ltp=120.0), _row("PE", SPOT, ltp=0.0))

    assert atm_straddle(only_call, SPOT) is None
    assert atm_straddle((), SPOT) is None
    assert atm_straddle(only_call, None) is None


def test_leg_ltp_treats_zero_as_unquoted() -> None:
    rows = (_row("CE", SPOT, ltp=0.0), _row("PE", SPOT, ltp=70.0))

    assert leg_ltp(rows, SPOT, is_call=True) is None
    assert leg_ltp(rows, SPOT, is_call=False) == 70.0


# -- the payload ------------------------------------------------------------


async def test_every_frame_shares_the_payloads_strike_axis() -> None:
    snaps = [_snap(0, _ladder()), _snap(30, _ladder())]

    payload = await _service(snaps)(TENANT, "NIFTY")

    width = len(payload["strikes"])
    assert width > 0
    for frame in payload["frames"]:
        assert len(frame["ce_ltp"]) == width
        assert len(frame["pe_ltp"]) == width


async def test_the_time_axis_matches_the_frames() -> None:
    snaps = [_snap(minute, _ladder()) for minute in (0, 15, 30)]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["t"] == [frame["t"] for frame in payload["frames"]]


async def test_the_rolling_atm_straddle_follows_the_money() -> None:
    # Morning ATM at 24650 with a 190 straddle; afternoon the ATM moves to 24700
    # with a different straddle. A payload-level straddle would show the morning
    # value against the afternoon frame.
    morning = _snap(0, _ladder(call_ltp={SPOT: 120.0}, put_ltp={SPOT: 70.0}), atm=SPOT)
    afternoon = _snap(
        240,
        _ladder(call_ltp={SPOT + 50.0: 60.0}, put_ltp={SPOT + 50.0: 150.0}),
        spot=SPOT + 50.0,
        atm=SPOT + 50.0,
    )

    payload = await _service([morning, afternoon])(TENANT, "NIFTY")

    assert payload["frames"][0]["atm_straddle"] == 190.0
    assert payload["frames"][1]["atm_straddle"] == 210.0


async def test_per_strike_ltps_align_to_the_axis() -> None:
    snaps = [_snap(0, _ladder()), _snap(30, _ladder())]

    payload = await _service(snaps)(TENANT, "NIFTY")

    strikes = payload["strikes"]
    atm_index = strikes.index(SPOT)
    frame = payload["frames"][-1]
    assert frame["ce_ltp"][atm_index] == 100.0
    assert frame["pe_ltp"][atm_index] == 90.0


async def test_the_future_is_emitted_per_frame() -> None:
    snaps = [_snap(0, _ladder()), _snap(30, _ladder())]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["frames"][-1]["future"] == 24_700.0


async def test_a_capture_with_no_spot_anywhere_is_dropped_not_zeroed() -> None:
    blind = [
        ChainSnapshot(captured_at=datetime(2026, 8, 4, 4, 0, tzinfo=UTC), rows=_ladder()),
        ChainSnapshot(captured_at=datetime(2026, 8, 4, 4, 30, tzinfo=UTC), rows=_ladder()),
    ]
    service = GetStraddleSeries(
        provider=_SpotlessProvider(), snapshots=StubReader(blind), now_utc=lambda: NOW
    )

    payload = await service(TENANT, "NIFTY")

    assert payload["frames"] == []
    assert payload["data_quality"] == "empty"


class _SpotlessProvider:
    async def fetch(self, tenant_id: TenantId, symbol: str) -> ProviderChain:
        return ProviderChain(rows=(), spot=None, lot_size=LOT, expiry=EXPIRY)


# -- degenerate days --------------------------------------------------------


async def test_an_empty_day_is_shaped_not_broken() -> None:
    payload = await _service([])(TENANT, "NIFTY")

    assert payload["data_quality"] == "empty"
    assert payload["frames"] == []
    assert payload["strikes"] == []
    assert payload["expiry_date"] == EXPIRY


async def test_a_single_capture_is_not_a_session() -> None:
    payload = await _service([_snap(0, _ladder())])(TENANT, "NIFTY")

    assert payload["data_quality"] == "empty"


# -- historical mode --------------------------------------------------------

# A past trading day; the stub reader ignores the date, so any past instant works.
PAST = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


async def test_historical_reads_the_archived_day() -> None:
    payload = await _service([_snap(0, _ladder()), _snap(30, _ladder())])(
        TENANT, "NIFTY", trade_date=PAST
    )

    assert payload["data_quality"] == "intraday"
    assert len(payload["t"]) == 2


async def test_historical_with_no_archive_is_empty() -> None:
    payload = await _service([])(TENANT, "NIFTY", trade_date=PAST)
    assert payload["data_quality"] == "empty"
