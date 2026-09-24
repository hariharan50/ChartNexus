"""The aggregate price-vs-OI series behind Future Lab → Price vs OI.

Pins the two things this page reads and the sibling per-contract series does not:
that the OI line sums the *whole chain* per frame, and that a picked ``trade_date``
replays that archived day rather than today.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from marketcompass.contexts.options_analytics.application.ports import (
    ChainSnapshot,
    ProviderChain,
)
from marketcompass.contexts.options_analytics.application.price_oi_series_service import (
    GetPriceOiSeries,
)
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())
# 08:00 UTC == 13:30 IST, inside the session on 2026-08-04.
NOW = datetime(2026, 8, 4, 8, 0, tzinfo=UTC)
OPEN = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)  # 09:15 IST


def _rows(*, oi: int, change: int = 0) -> tuple[ChainRow, ...]:
    # Three strikes, both sides — six legs, so total OI is 6 * oi.
    return tuple(
        ChainRow(
            strike=strike, option_type=side, oi=oi, oi_change=change, ltp=10.0, volume=0, iv=None
        )
        for strike in (24_600.0, 24_650.0, 24_700.0)
        for side in ("CE", "PE")
    )


def _snap(minutes: int, *, oi: int, change: int = 0, **header) -> ChainSnapshot:
    return ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 3, 45, tzinfo=UTC).replace(
            hour=3 + (45 + minutes) // 60, minute=(45 + minutes) % 60
        ),
        rows=_rows(oi=oi, change=change),
        spot=header.get("spot", 24_650.0),
        atm_strike=header.get("atm_strike", 24_650.0),
        future_price=header.get("future_price"),
    )


class StubProvider:
    async def fetch(
        self, tenant_id: TenantId, symbol: str, *, expiry: str | None = None
    ) -> ProviderChain:
        return ProviderChain(rows=_rows(oi=100), spot=24_650.0, lot_size=75, expiry="2026-08-11")


class StubReader:
    def __init__(self, snapshots: list[ChainSnapshot]) -> None:
        self._snapshots = snapshots
        self.asked_for: datetime | None = None

    async def latest_in_session(self, tenant_id, symbol, *, now_utc):  # type: ignore[no-untyped-def]
        return self._snapshots[-1] if self._snapshots else None

    async def day_snapshots(self, tenant_id, symbol, *, trade_date_utc):  # type: ignore[no-untyped-def]
        self.asked_for = trade_date_utc
        return list(self._snapshots)


def _service(snapshots: list[ChainSnapshot], reader: StubReader | None = None) -> GetPriceOiSeries:
    return GetPriceOiSeries(
        provider=StubProvider(),
        snapshots=reader or StubReader(snapshots),
        now_utc=lambda: NOW,
    )


async def test_shared_axis_with_price_and_total_oi() -> None:
    snaps = [_snap(0, oi=100, future_price=24_700.0), _snap(1, oi=110, future_price=24_705.0)]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["data_quality"] == "intraday"
    assert payload["t"] and len(payload["price"]) == len(payload["t"]) == len(payload["oi"])
    # Six legs per frame → total OI is 6 * per-leg.
    assert payload["oi"] == [600, 660]
    # The line plots the tradable future, not spot.
    assert payload["price"] == [24_700.0, 24_705.0]


async def test_oi_sums_the_whole_chain_not_a_window() -> None:
    # A far strike well outside any ATM window still counts toward the total.
    wide = ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 4, 0, tzinfo=UTC),
        rows=(
            ChainRow(
                strike=24_650.0, option_type="CE", oi=100, oi_change=0, ltp=1, volume=0, iv=None
            ),
            ChainRow(
                strike=30_000.0, option_type="CE", oi=500, oi_change=0, ltp=1, volume=0, iv=None
            ),
        ),
        spot=24_650.0,
        atm_strike=24_650.0,
    )
    earlier = ChainSnapshot(captured_at=datetime(2026, 8, 4, 3, 46, tzinfo=UTC), rows=wide.rows)

    payload = await _service([earlier, wide])(TENANT, "NIFTY")

    assert payload["oi"][-1] == 600  # 100 + 500, the far strike included


async def test_price_is_none_on_the_reconstructed_open() -> None:
    late = _snap(75, oi=500, change=200)  # 10:30 IST — nobody recorded 09:15
    later = _snap(105, oi=700, change=400)

    payload = await _service([late, later])(TENANT, "NIFTY")

    assert payload["open_is_estimated"] is True
    assert payload["t"][0] == OPEN.isoformat()
    # 700 - 400 = 300 per leg at the open, six legs.
    assert payload["oi"][0] == 300 * 6
    # Nothing recorded the index at the bell, so the line starts where recording does.
    assert payload["price"][0] is None


async def test_unarchived_day_falls_back_to_open_vs_now() -> None:
    payload = await _service([])(TENANT, "NIFTY")

    assert payload["data_quality"] == "live_proxy"
    assert payload["open_is_estimated"] is True
    assert payload["t"] == ["2026-08-04T03:45:00+00:00", "2026-08-04T08:00:00+00:00"]


async def test_before_the_bell_is_empty() -> None:
    service = GetPriceOiSeries(
        provider=StubProvider(),
        snapshots=StubReader([]),
        now_utc=lambda: datetime(2026, 8, 4, 2, 30, tzinfo=UTC),
    )

    payload = await service(TENANT, "NIFTY")

    assert payload["data_quality"] == "empty"
    assert payload["t"] == []
    assert payload["price"] == []
    assert payload["oi"] == []


async def test_historical_reads_the_picked_day() -> None:
    reader = StubReader([_snap(0, oi=100), _snap(1, oi=110)])
    past = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)

    await _service([], reader)(TENANT, "NIFTY", trade_date=past)

    # The reader was asked for the picked day, not today.
    assert reader.asked_for == past


async def test_a_coarser_interval_thins_the_series() -> None:
    snaps = [_snap(minute, oi=100 + minute) for minute in range(30)]

    fine = await _service(snaps)(TENANT, "NIFTY", interval="1m")
    coarse = await _service(snaps)(TENANT, "NIFTY", interval="15m")

    assert len(coarse["t"]) < len(fine["t"])
    assert coarse["oi"][-1] == fine["oi"][-1]
