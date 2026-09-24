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
    async def fetch(
        self, tenant_id: TenantId, symbol: str, *, expiry: str | None = None
    ) -> ProviderChain:
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


# -- captures that have not happened yet ------------------------------------


async def test_future_snapshots_are_ignored() -> None:
    """The archive must never report a market that does not exist yet.

    Real ingest cannot write ahead of itself, but a seeded or restored day can.
    The visible symptom was the tool's "as of" handle reading 3:30 pm at 11:55,
    with the newest frame's spot and OI taken from a capture in the future.
    """
    early = ChainSnapshot(datetime(2026, 8, 4, 3, 45, tzinfo=UTC), _rows(200, 500))
    current = ChainSnapshot(datetime(2026, 8, 4, 5, 45, tzinfo=UTC), _rows(300, 300))
    ahead = ChainSnapshot(datetime(2026, 8, 4, 9, 30, tzinfo=UTC), _rows(900, 900))

    payload = await _view([early, current, ahead])(TENANT, "NIFTY")

    assert payload["data_quality"] == "intraday"
    assert len(payload["series"]) == 2
    assert payload["now_ts"].startswith("2026-08-04T05:45")
    # The future capture's 900-per-leg would have shown as 1800.
    assert payload["total_call_oi"] == 600


async def test_a_capture_on_the_current_instant_is_kept() -> None:
    # The cutoff is inclusive: the tick that just landed is the newest frame,
    # not one to discard.
    early = ChainSnapshot(datetime(2026, 8, 4, 3, 45, tzinfo=UTC), _rows(200, 500))
    right_now = ChainSnapshot(NOW, _rows(300, 300))

    payload = await _view([early, right_now])(TENANT, "NIFTY")

    assert payload["data_quality"] == "intraday"
    assert len(payload["series"]) == 2


async def test_dropping_future_captures_can_degrade_the_tier() -> None:
    # Honest degradation: if everything but one capture is in the future, there
    # is only one real observation and the proxy tier is the truthful answer.
    current = ChainSnapshot(datetime(2026, 8, 4, 5, 45, tzinfo=UTC), _rows(300, 300))
    ahead = ChainSnapshot(datetime(2026, 8, 4, 9, 30, tzinfo=UTC), _rows(900, 900))

    payload = await _view([current, ahead])(TENANT, "NIFTY")

    assert payload["data_quality"] == "live_proxy"


# -- a morning nobody captured ----------------------------------------------


def _rows_with_change(oi: int, change: int) -> tuple[ChainRow, ...]:
    return (
        ChainRow(strike=100.0, option_type="CE", oi=oi, oi_change=change, ltp=10.0, volume=1),
        ChainRow(strike=100.0, option_type="PE", oi=oi, oi_change=change, ltp=9.0, volume=1),
    )


async def test_the_session_open_is_reconstructed_when_it_was_never_captured() -> None:
    """A worker that starts at lunchtime must not redefine "the open".

    Without this the baseline handle sits at the first stored capture, and "OI
    change" silently means "change since lunchtime" — the most-read number on
    the page, quietly wrong. `oi_change` is the broker's change since the
    session open, so `oi - oi_change` is the 09:15 book.
    """
    # 05:00 and 05:45 UTC are 10:30 and 11:15 IST — well past the bell, and
    # before the frozen NOW, so neither is dropped as a future capture.
    late = ChainSnapshot(datetime(2026, 8, 4, 5, 0, tzinfo=UTC), _rows_with_change(500, 200))
    later = ChainSnapshot(datetime(2026, 8, 4, 5, 45, tzinfo=UTC), _rows_with_change(700, 400))

    payload = await _view([late, later])(TENANT, "NIFTY")

    assert payload["open_is_estimated"] is True
    # 09:15 IST is 03:45 UTC.
    assert payload["open_ts"].startswith("2026-08-04T03:45")
    assert payload["series"][0]["t"].startswith("2026-08-04T03:45")
    # 700 - 400 = 300 at the open, read off the newest snapshot.
    assert payload["series"][0]["call"][0] == 300
    assert payload["total_call_oi_chg"] == 400


async def test_a_captured_open_is_not_second_guessed() -> None:
    # 03:45 UTC is the bell itself. The stored frame wins; nothing is invented.
    at_open = ChainSnapshot(datetime(2026, 8, 4, 3, 45, tzinfo=UTC), _rows_with_change(300, 0))
    later = ChainSnapshot(datetime(2026, 8, 4, 5, 45, tzinfo=UTC), _rows_with_change(700, 400))

    payload = await _view([at_open, later])(TENANT, "NIFTY")

    assert payload["open_is_estimated"] is False
    assert len(payload["series"]) == 2


async def test_a_capture_just_after_the_bell_still_reconstructs_the_open() -> None:
    """Even one minute late, 09:15 is reconstructed rather than assumed.

    `oi_change` is the change *since the bell*, so a snapshot taken after 09:15
    already reports an OI that has moved off the open. Anchoring the baseline to
    it would make "OI change" understate the real move by that drift — the bug
    that had 24300 PE reading -27.54L against Kite/StockMojo's -37.5L. The busy
    strikes shift most in the first minute, so this is exactly where it bites.

    Here the near-open capture happens to carry `oi_change=0`, so the
    reconstructed open (700 - 400 = 300) agrees with it — but the number now
    comes from the broker's day-change, not from a snapshot we hope is close
    enough.
    """
    # 03:48 UTC is 09:18 IST — three minutes into the session, no 09:15 capture.
    nearly = ChainSnapshot(datetime(2026, 8, 4, 3, 48, tzinfo=UTC), _rows_with_change(300, 0))
    later = ChainSnapshot(datetime(2026, 8, 4, 5, 45, tzinfo=UTC), _rows_with_change(700, 400))

    payload = await _view([nearly, later])(TENANT, "NIFTY")

    assert payload["open_is_estimated"] is True
    # 09:15 IST is 03:45 UTC — the reconstructed open, not the 03:48 capture.
    assert payload["open_ts"].startswith("2026-08-04T03:45")
    assert payload["series"][0]["call"][0] == 300
    assert payload["total_call_oi_chg"] == 400


async def test_the_reconstructed_open_never_goes_negative() -> None:
    # A broker reporting a change larger than the current OI is nonsense, but it
    # must not produce negative open interest on the chart.
    late = ChainSnapshot(datetime(2026, 8, 4, 5, 0, tzinfo=UTC), _rows_with_change(100, 900))
    later = ChainSnapshot(datetime(2026, 8, 4, 5, 45, tzinfo=UTC), _rows_with_change(100, 900))

    payload = await _view([late, later])(TENANT, "NIFTY")

    assert payload["series"][0]["call"][0] == 0


# -- historical mode --------------------------------------------------------

# A past trading day; the stub reader ignores the date, so any past instant works.
PAST = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


async def test_historical_reads_the_archived_day() -> None:
    open_snap = ChainSnapshot(datetime(2026, 8, 4, 3, 45, tzinfo=UTC), _rows(200, 500))
    now_snap = ChainSnapshot(datetime(2026, 8, 4, 5, 45, tzinfo=UTC), _rows(300, 300))

    payload = await _view([open_snap, now_snap])(TENANT, "NIFTY", trade_date=PAST)

    assert payload["data_quality"] == "intraday"
    assert payload["total_call_oi"] == 600


async def test_historical_with_no_archive_is_empty_not_live() -> None:
    # A past day with nothing captured must not borrow today's live chain.
    historical = await _view([])(TENANT, "NIFTY", trade_date=PAST)
    assert historical["data_quality"] == "empty"

    live = await _view([])(TENANT, "NIFTY")
    assert live["data_quality"] == "live_proxy"
