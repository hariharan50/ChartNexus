"""The per-contract series behind Multi OI & Volume.

The shape of this payload is what three stacked charts read directly, so the
things pinned here are the ones that would silently draw a wrong picture: which
snapshot survives a bucket, which price the overlay uses, and how a leg that
stops being quoted behaves.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from marketcompass.contexts.options_analytics.application.oi_series_service import GetOiSeries
from marketcompass.contexts.options_analytics.application.ports import (
    ChainSnapshot,
    ProviderChain,
)
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())
# 08:00 UTC == 13:30 IST, inside the session on 2026-08-04.
NOW = datetime(2026, 8, 4, 8, 0, tzinfo=UTC)
# 09:15 IST.
OPEN = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)


def _rows(*, oi: int, change: int = 0, volume: int = 0) -> tuple[ChainRow, ...]:
    return tuple(
        ChainRow(
            strike=strike,
            option_type=side,
            oi=oi,
            oi_change=change,
            ltp=10.0,
            volume=volume,
            iv=None,
        )
        for strike in (24_600.0, 24_650.0, 24_700.0)
        for side in ("CE", "PE")
    )


def _snap(minutes: int, *, oi: int, change: int = 0, volume: int = 0, **header) -> ChainSnapshot:
    return ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 3, 45, tzinfo=UTC).replace(
            hour=3 + (45 + minutes) // 60, minute=(45 + minutes) % 60
        ),
        rows=_rows(oi=oi, change=change, volume=volume),
        spot=header.get("spot", 24_650.0),
        atm_strike=header.get("atm_strike", 24_650.0),
        future_price=header.get("future_price"),
    )


class StubProvider:
    async def fetch(self, tenant_id: TenantId, symbol: str) -> ProviderChain:
        return ProviderChain(rows=_rows(oi=100), spot=24_650.0, lot_size=75, expiry="2026-08-11")


class StubReader:
    def __init__(self, snapshots: list[ChainSnapshot]) -> None:
        self._snapshots = snapshots

    async def latest_in_session(self, tenant_id, symbol, *, now_utc):  # type: ignore[no-untyped-def]
        return self._snapshots[-1] if self._snapshots else None

    async def day_snapshots(self, tenant_id, symbol, *, trade_date_utc):  # type: ignore[no-untyped-def]
        return list(self._snapshots)


def _service(snapshots: list[ChainSnapshot]) -> GetOiSeries:
    return GetOiSeries(
        provider=StubProvider(), snapshots=StubReader(snapshots), now_utc=lambda: NOW
    )


# -- shape ------------------------------------------------------------------


async def test_a_shared_axis_with_one_entry_per_contract() -> None:
    snaps = [_snap(0, oi=100), _snap(1, oi=110), _snap(2, oi=120)]

    payload = await _service(snaps)(TENANT, "NIFTY", interval="1m")

    assert payload["data_quality"] == "intraday"
    assert len(payload["t"]) == 3
    # Three strikes, both sides.
    assert len(payload["contracts"]) == 6
    for contract in payload["contracts"]:
        assert len(contract["oi"]) == len(payload["t"])
        assert len(contract["volume"]) == len(payload["t"])
        # Derived on the client; sending it too would be a second source of truth.
        assert "oi_change" not in contract


async def test_contract_ids_name_the_strike_and_side() -> None:
    payload = await _service([_snap(0, oi=100), _snap(1, oi=110)])(TENANT, "NIFTY")

    assert {"24600CE", "24600PE", "24650CE", "24700PE"} <= {
        contract["id"] for contract in payload["contracts"]
    }


async def test_an_empty_day_is_shaped_not_broken() -> None:
    # Before two captures land there is genuinely nothing to draw. The page
    # should say so rather than fail.
    payload = await _service([])(TENANT, "NIFTY")

    assert payload["data_quality"] == "empty"
    assert payload["t"] == []
    assert payload["contracts"] == []
    assert payload["default_ids"] == []


# -- bucketing --------------------------------------------------------------


async def test_a_bucket_keeps_its_last_snapshot_not_a_mean() -> None:
    """Open interest is a stock, not a flow.

    Averaging a bucket would print a reading the market never showed, and the
    final bucket would lag the live figure the rest of the page displays.
    """
    snaps = [_snap(minute, oi=100 + minute) for minute in range(10)]

    payload = await _service(snaps)(TENANT, "NIFTY", interval="5m")

    contract = payload["contracts"][0]
    # Buckets [0-4] and [5-9] → the 5th and 10th readings, not their means.
    assert contract["oi"] == [100, 104, 109]


async def test_a_coarser_interval_thins_the_series_without_reshaping_it() -> None:
    snaps = [_snap(minute, oi=100 + minute) for minute in range(30)]

    fine = await _service(snaps)(TENANT, "NIFTY", interval="1m")
    coarse = await _service(snaps)(TENANT, "NIFTY", interval="15m")

    assert len(coarse["t"]) < len(fine["t"])
    # Whatever the bucket, both end on the same live reading.
    assert coarse["contracts"][0]["oi"][-1] == fine["contracts"][0]["oi"][-1]


async def test_an_unknown_interval_falls_back_rather_than_failing() -> None:
    payload = await _service([_snap(0, oi=100), _snap(1, oi=110)])(TENANT, "NIFTY", interval="7s")

    assert len(payload["t"]) == 2


# -- the futures overlay ----------------------------------------------------


async def test_the_overlay_plots_the_future_not_spot() -> None:
    # On a chart of option positions the index level is the one price nobody in
    # the picture can deal at.
    snaps = [
        _snap(0, oi=100, spot=24_650.0, future_price=24_700.0),
        _snap(1, oi=110, spot=24_655.0, future_price=24_705.0),
    ]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["fut"] == [24_700.0, 24_705.0]


async def test_the_overlay_falls_back_to_spot_when_no_future_was_stored() -> None:
    snaps = [_snap(0, oi=100, future_price=None), _snap(1, oi=110, future_price=None)]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["fut"] == [24_650.0, 24_650.0]


# -- defaults ---------------------------------------------------------------


async def test_defaults_rank_by_the_latest_reading_of_each_measure() -> None:
    busy = ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 4, 0, tzinfo=UTC),
        rows=(
            ChainRow(strike=24_600.0, option_type="CE", oi=900, oi_change=0, ltp=1, volume=5),
            ChainRow(strike=24_650.0, option_type="CE", oi=100, oi_change=0, ltp=1, volume=900),
        ),
        spot=24_650.0,
        atm_strike=24_650.0,
    )
    quiet = ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 3, 46, tzinfo=UTC),
        rows=busy.rows,
        spot=24_650.0,
        atm_strike=24_650.0,
    )

    payload = await _service([quiet, busy])(TENANT, "NIFTY")

    assert payload["default_ids"][0] == "24600CE"
    assert payload["default_vol_ids"][0] == "24650CE"


# -- gaps and the reconstructed open ----------------------------------------


async def test_a_late_start_gets_the_reconstructed_open_at_index_zero() -> None:
    # 05:00 UTC is 10:30 IST — well past the bell, so nobody recorded 09:15.
    late = ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 5, 0, tzinfo=UTC),
        rows=_rows(oi=500, change=200),
        spot=24_650.0,
        atm_strike=24_650.0,
    )
    later = ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 5, 30, tzinfo=UTC),
        rows=_rows(oi=700, change=400),
        spot=24_650.0,
        atm_strike=24_650.0,
    )

    payload = await _service([late, later])(TENANT, "NIFTY")

    assert payload["open_is_estimated"] is True
    assert payload["t"][0] == OPEN.isoformat()
    # 700 - 400 = 300 at the open, read off the newest snapshot.
    assert payload["contracts"][0]["oi"][0] == 300
    # Nothing recorded the index at 09:15, so the overlay starts where the
    # recording does rather than reaching back to an invented level.
    assert payload["fut"][0] is None


async def test_a_leg_that_stops_being_quoted_holds_its_last_value() -> None:
    """A contract dropping off the chain did not have its open interest wiped.

    Reading zero would draw the line to the axis and say exactly that.
    """
    full = _snap(0, oi=100)
    thinned = ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 3, 46, tzinfo=UTC),
        rows=tuple(row for row in _rows(oi=150) if row.strike != 24_600.0),
        spot=24_650.0,
        atm_strike=24_650.0,
    )

    payload = await _service([full, thinned])(TENANT, "NIFTY")

    by_id = {contract["id"]: contract for contract in payload["contracts"]}
    assert "24600CE" in by_id, "a delisted strike must stay in the ladder"
    assert by_id["24600CE"]["oi"] == [100, 100]


# -- window -----------------------------------------------------------------


@pytest.mark.parametrize(("requested", "expected"), [(0, 1), (1, 1), (5, 5), (999, 40)])
async def test_the_window_is_clamped_to_something_survivable(requested: int, expected: int) -> None:
    # The window bounds the payload, so an unbounded value would be a way to ask
    # the server for an arbitrarily large response.
    payload = await _service([_snap(0, oi=100), _snap(1, oi=110)])(
        TENANT, "NIFTY", window=requested
    )

    assert payload["window"] == expected


async def test_a_narrow_window_keeps_only_strikes_near_the_money() -> None:
    payload = await _service([_snap(0, oi=100), _snap(1, oi=110)])(TENANT, "NIFTY", window=1)

    strikes = {contract["strike"] for contract in payload["contracts"]}
    assert strikes == {24_600.0, 24_650.0, 24_700.0}
