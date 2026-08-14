"""Chain-wide totals behind the Put-Call Ratio tool.

The ratio is the point of the page, so the cases pinned here are the ones that
would draw a confident wrong line: an undefined ratio rendered as a number, and
change totals derived the convenient way rather than the correct one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from marketcompass.contexts.options_analytics.application.pcr_series_service import GetPcrSeries
from marketcompass.contexts.options_analytics.application.ports import (
    ChainSnapshot,
    ProviderChain,
)
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow, pcr_oi
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())
# 08:00 UTC == 13:30 IST, inside the session on 2026-08-04.
NOW = datetime(2026, 8, 4, 8, 0, tzinfo=UTC)
# 09:15 IST.
OPEN = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)


def _row(side: str, oi: int, change: int, strike: float = 24_650.0) -> ChainRow:
    return ChainRow(
        strike=strike, option_type=side, oi=oi, oi_change=change, ltp=10.0, volume=1, iv=None
    )


def _snap(
    minute: int,
    *,
    call_oi: int,
    put_oi: int,
    call_chg: int = 0,
    put_chg: int = 0,
    future: float | None = 24_700.0,
) -> ChainSnapshot:
    # Anchored at the bell, so these fixtures get no reconstructed open — that
    # path has its own test below, and a surprise extra point at index 0 would
    # make every exact-array assertion here read as a failure of something else.
    return ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 3, 45 + minute, tzinfo=UTC),
        rows=(_row("CE", call_oi, call_chg), _row("PE", put_oi, put_chg)),
        spot=24_650.0,
        atm_strike=24_650.0,
        future_price=future,
    )


class StubProvider:
    async def fetch(self, tenant_id: TenantId, symbol: str) -> ProviderChain:
        return ProviderChain(rows=(), spot=24_650.0, lot_size=75, expiry="2026-08-11")


class StubReader:
    def __init__(self, snapshots: list[ChainSnapshot]) -> None:
        self._snapshots = snapshots

    async def latest_in_session(self, tenant_id, symbol, *, now_utc):  # type: ignore[no-untyped-def]
        return self._snapshots[-1] if self._snapshots else None

    async def day_snapshots(self, tenant_id, symbol, *, trade_date_utc):  # type: ignore[no-untyped-def]
        return list(self._snapshots)


def _service(snapshots: list[ChainSnapshot]) -> GetPcrSeries:
    return GetPcrSeries(
        provider=StubProvider(), snapshots=StubReader(snapshots), now_utc=lambda: NOW
    )


# -- the ratio --------------------------------------------------------------


async def test_the_ratio_is_puts_over_calls() -> None:
    snaps = [_snap(0, call_oi=1_000, put_oi=800), _snap(1, call_oi=1_000, put_oi=1_200)]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["pcr"] == [0.8, 1.2]


async def test_the_ratio_matches_the_open_interest_page() -> None:
    # Both pages must mean the same thing by "PCR"; a chart that disagreed with
    # the headline figure beside it would be worse than either being wrong.
    rows = (_row("CE", 1_000, 0), _row("PE", 1_450, 0))
    snaps = [_snap(0, call_oi=1_000, put_oi=1_450), _snap(1, call_oi=1_000, put_oi=1_450)]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["pcr"][-1] == pcr_oi(rows)


async def test_an_undefined_ratio_is_null_not_zero() -> None:
    """No call interest is a divide-by-zero, not a ratio of nothing.

    `oi_math.pcr_oi` answers 0.0 there because a headline figure has to render
    something. A line is different: 0 draws a floor the market never printed and
    drags the axis down to it. `None` breaks the line, which is the truth.
    """
    snaps = [
        _snap(0, call_oi=0, put_oi=900),
        _snap(1, call_oi=1_000, put_oi=900),
    ]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["pcr"][0] is None
    assert payload["pcr"][1] == 0.9


# -- totals -----------------------------------------------------------------


async def test_change_totals_sum_the_legs_own_day_change() -> None:
    # Not differenced against the open. The broker's `oi_change` is the
    # authority, and the two diverge the moment a strike is delisted.
    snaps = [
        _snap(0, call_oi=1_000, put_oi=900, call_chg=100, put_chg=200),
        _snap(1, call_oi=1_400, put_oi=1_500, call_chg=400, put_chg=600),
    ]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["call_oi_chg"] == [100, 400]
    assert payload["put_oi_chg"] == [200, 600]
    assert payload["call_oi"] == [1_000, 1_400]
    assert payload["put_oi"] == [900, 1_500]


async def test_every_array_is_aligned_to_the_time_axis() -> None:
    snaps = [_snap(minute, call_oi=1_000, put_oi=900) for minute in range(4)]

    payload = await _service(snaps)(TENANT, "NIFTY")

    length = len(payload["t"])
    for key in ("fut", "pcr", "call_oi", "put_oi", "call_oi_chg", "put_oi_chg"):
        assert len(payload[key]) == length, key


# -- the futures overlay ----------------------------------------------------


async def test_the_overlay_plots_the_future_not_spot() -> None:
    snaps = [
        _snap(0, call_oi=1_000, put_oi=900, future=24_700.0),
        _snap(1, call_oi=1_000, put_oi=900, future=24_705.0),
    ]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["fut"] == [24_700.0, 24_705.0]


async def test_the_overlay_falls_back_to_spot_when_none_was_stored() -> None:
    snaps = [
        _snap(0, call_oi=1_000, put_oi=900, future=None),
        _snap(1, call_oi=1_000, put_oi=900, future=None),
    ]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["fut"] == [24_650.0, 24_650.0]


# -- the reconstructed open -------------------------------------------------


async def test_a_late_start_gets_the_reconstructed_open_at_index_zero() -> None:
    # 05:00 UTC is 10:30 IST — nobody recorded the bell, so PCR at the open has
    # to come from the day-change field. It is the number every later reading is
    # judged against.
    late = ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 5, 0, tzinfo=UTC),
        rows=(_row("CE", 1_500, 500), _row("PE", 1_800, 900)),
        spot=24_650.0,
        future_price=24_700.0,
    )
    later = ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 5, 30, tzinfo=UTC),
        rows=(_row("CE", 2_000, 1_000), _row("PE", 2_400, 1_500)),
        spot=24_650.0,
        future_price=24_710.0,
    )

    payload = await _service([late, later])(TENANT, "NIFTY")

    assert payload["open_is_estimated"] is True
    assert payload["t"][0] == OPEN.isoformat()
    # Calls opened at 2000-1000, puts at 2400-1500 → 900/1000.
    assert payload["call_oi"][0] == 1_000
    assert payload["put_oi"][0] == 900
    assert payload["pcr"][0] == 0.9
    # Nothing recorded the market at 09:15, so the price line starts where the
    # recording does rather than at an invented level.
    assert payload["fut"][0] is None
    # A reconstructed open has, by definition, no change yet.
    assert payload["call_oi_chg"][0] == 0
    assert payload["put_oi_chg"][0] == 0


# -- degenerate days --------------------------------------------------------


async def test_an_empty_day_is_shaped_not_broken() -> None:
    # Nothing archived *and* no live chain to proxy from: there is genuinely
    # nothing to draw, and the page says so rather than failing.
    payload = await _service([])(TENANT, "NIFTY")

    assert payload["data_quality"] == "empty"
    assert payload["t"] == []
    assert payload["pcr"] == []
    assert payload["expiry_date"] == "2026-08-11"


async def test_a_single_capture_becomes_open_vs_now() -> None:
    """One point is a reading, not a line — so the open is reconstructed beside it.

    The Open Interest page has always served this tier; leaving it out here left
    the three charts blank all session on any machine without an ingest worker.
    """
    snap = _snap(0, call_oi=1_000, put_oi=900, call_chg=200, put_chg=300)

    payload = await _service([snap])(TENANT, "NIFTY")

    assert payload["data_quality"] == "live_proxy"
    assert payload["open_is_estimated"] is True
    assert payload["t"] == ["2026-08-04T03:45:00+00:00", "2026-08-04T08:00:00+00:00"]
    # Opened at 800/600 — `oi - oi_change`, the broker's own day-change field.
    assert payload["call_oi"] == [800, 1_000]
    assert payload["put_oi"] == [600, 900]
    assert payload["call_oi_chg"] == [0, 200]
    assert payload["put_oi_chg"] == [0, 300]


# -- historical mode --------------------------------------------------------

# A past trading day; the stub reader ignores the date, so any past instant works.
PAST = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


async def test_historical_reads_the_archived_day() -> None:
    snaps = [_snap(0, call_oi=1_000, put_oi=800), _snap(1, call_oi=1_000, put_oi=1_200)]

    payload = await _service(snaps)(TENANT, "NIFTY", trade_date=PAST)

    assert payload["data_quality"] == "intraday"
    assert payload["pcr"] == [0.8, 1.2]


async def test_historical_with_no_archive_is_empty() -> None:
    # A past day with nothing captured is empty — it must not borrow today's chain.
    historical = await _service([])(TENANT, "NIFTY", trade_date=PAST)
    assert historical["data_quality"] == "empty"
