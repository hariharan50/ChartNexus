"""The tier the Historic feature activates.

``GetOiView`` already knew how to serve real intraday history; it was starved of
snapshots. These tests prove that a ``SnapshotReader`` yielding two-plus captures
flips the payload from the live proxy to the intraday tier — the observable
effect of the whole feature — and that a single capture still degrades cleanly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from marketcompass.contexts.options_analytics.application.oi_service import GetOiView
from marketcompass.contexts.options_analytics.application.ports import (
    ChainSnapshot,
    ProviderChain,
)
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())
NOW = datetime(2026, 8, 4, 6, 0, tzinfo=UTC)


def _rows(call_oi: int, put_oi: int) -> tuple[ChainRow, ...]:
    return (
        ChainRow(strike=100.0, option_type="CE", oi=call_oi, oi_change=0, ltp=10.0, volume=1),
        ChainRow(strike=100.0, option_type="PE", oi=put_oi, oi_change=0, ltp=9.0, volume=1),
        ChainRow(strike=110.0, option_type="CE", oi=call_oi, oi_change=0, ltp=6.0, volume=1),
        ChainRow(strike=110.0, option_type="PE", oi=put_oi, oi_change=0, ltp=5.0, volume=1),
    )


class StubProvider:
    async def fetch(self, tenant_id: TenantId, symbol: str) -> ProviderChain:
        return ProviderChain(rows=_rows(300, 300), spot=104.0, lot_size=75, expiry="2026-08-07")


class StubReader:
    def __init__(self, snapshots: list[ChainSnapshot]) -> None:
        self._snapshots = snapshots

    async def latest_in_session(self, tenant_id, symbol, *, now_utc):  # type: ignore[no-untyped-def]
        return self._snapshots[-1] if self._snapshots else None

    async def day_snapshots(self, tenant_id, symbol, *, trade_date_utc):  # type: ignore[no-untyped-def]
        return list(self._snapshots)


def _view(snapshots: list[ChainSnapshot]) -> GetOiView:
    return GetOiView(provider=StubProvider(), snapshots=StubReader(snapshots), now_utc=lambda: NOW)


async def test_two_snapshots_activate_the_intraday_tier() -> None:
    open_snap = ChainSnapshot(datetime(2026, 8, 4, 3, 45, tzinfo=UTC), _rows(200, 500))
    now_snap = ChainSnapshot(datetime(2026, 8, 4, 5, 45, tzinfo=UTC), _rows(300, 300))

    payload = await _view([open_snap, now_snap])(TENANT, "NIFTY")

    assert payload["data_quality"] == "intraday"
    # Real open vs now: call OI opened at 400 (2x200) and is now 600 (2x300).
    assert payload["total_call_oi"] == 600
    assert payload["total_call_oi_chg"] == 200
    # The series carries one frame per capture, not a two-point proxy.
    assert len(payload["series"]) == 2


async def test_single_snapshot_falls_back_to_live_proxy() -> None:
    only = ChainSnapshot(datetime(2026, 8, 4, 5, 45, tzinfo=UTC), _rows(300, 300))

    payload = await _view([only])(TENANT, "NIFTY")

    assert payload["data_quality"] == "live_proxy"


async def test_no_snapshots_serves_live() -> None:
    payload = await _view([])(TENANT, "NIFTY")

    assert payload["data_quality"] == "live_proxy"  # LIVE tier reuses the proxy shape
