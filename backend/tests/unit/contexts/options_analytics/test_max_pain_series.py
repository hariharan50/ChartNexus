"""Max pain through the session, behind the Intraday Max Pain chart.

The cases pinned here are the ones that would draw a confident wrong line: a
reconstructed 09:15 frame opening the series with a hole, a price of zero
dragging the shared axis to the floor, and a past day quietly answered with
today's live chain.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from marketcompass.contexts.options_analytics.application.max_pain_series_service import (
    GetMaxPainSeries,
)
from marketcompass.contexts.options_analytics.application.ports import (
    ChainSnapshot,
    ProviderChain,
)
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow, max_pain
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())
# 08:00 UTC == 13:30 IST, inside the session on 2026-08-04.
NOW = datetime(2026, 8, 4, 8, 0, tzinfo=UTC)
# 09:15 IST - the bell.
BELL = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)


def _row(side: str, oi: int, change: int = 0, strike: float = 24_650.0) -> ChainRow:
    return ChainRow(
        strike=strike, option_type=side, oi=oi, oi_change=change, ltp=10.0, volume=1, iv=None
    )


def _ladder(call_heavy_at: float) -> tuple[ChainRow, ...]:
    """A three-strike book whose max pain is pinned by where the calls sit."""
    strikes = (24_600.0, 24_650.0, 24_700.0)
    rows: list[ChainRow] = []
    for strike in strikes:
        rows.append(_row("CE", 5_000 if strike == call_heavy_at else 100, strike=strike))
        rows.append(_row("PE", 100, strike=strike))
    return tuple(rows)


def _snap(
    minute: int,
    *,
    pain: float | None,
    future: float | None = 24_700.0,
    rows: tuple[ChainRow, ...] | None = None,
) -> ChainSnapshot:
    # Anchored at the bell, so these fixtures get no reconstructed open - that
    # path has its own test below, and a surprise extra point at index 0 would
    # make every exact-array assertion here read as a failure of something else.
    return ChainSnapshot(
        captured_at=BELL + timedelta(minutes=minute),
        rows=rows if rows is not None else (_row("CE", 1_000, 10), _row("PE", 900, -10)),
        spot=24_650.0,
        atm_strike=24_650.0,
        max_pain=pain,
        future_price=future,
    )


class StubProvider:
    def __init__(self, rows: tuple[ChainRow, ...] = (), spot: float = 24_650.0) -> None:
        self._rows = rows
        self._spot = spot

    async def fetch(self, tenant_id: TenantId, symbol: str) -> ProviderChain:
        return ProviderChain(rows=self._rows, spot=self._spot, lot_size=75, expiry="2026-08-11")


class StubReader:
    def __init__(self, snapshots: list[ChainSnapshot]) -> None:
        self._snapshots = snapshots

    async def latest_in_session(self, tenant_id, symbol, *, now_utc):  # type: ignore[no-untyped-def]
        return self._snapshots[-1] if self._snapshots else None

    async def day_snapshots(self, tenant_id, symbol, *, trade_date_utc):  # type: ignore[no-untyped-def]
        return list(self._snapshots)


def _service(  # type: ignore[no-untyped-def]
    snapshots: list[ChainSnapshot],
    *,
    chain_rows: tuple[ChainRow, ...] = (),
    chain_spot: float = 24_650.0,
):
    return GetMaxPainSeries(
        provider=StubProvider(chain_rows, chain_spot),
        snapshots=StubReader(snapshots),
        now_utc=lambda: NOW,
    )


class TestIntradayTier:
    async def test_the_stored_figure_is_read_straight_through(self) -> None:
        """The ingest worker already prices max pain at capture time.

        Re-pricing 375 strikes against 750 legs eighty times a request would be
        slow *and* risk disagreeing with the bar chart on the same page.
        """
        service = _service([_snap(0, pain=24_600.0), _snap(30, pain=24_650.0)])

        payload = await service(TENANT, "NIFTY")

        assert payload["data_quality"] == "intraday"
        assert payload["max_pain"] == [24_600.0, 24_650.0]

    async def test_every_series_stays_aligned_with_the_timestamps(self) -> None:
        """A short array silently shifts the whole chart against its own axis."""
        service = _service(
            [_snap(0, pain=24_600.0), _snap(30, pain=24_650.0, future=None), _snap(60, pain=None)]
        )

        payload = await service(TENANT, "NIFTY")

        assert len(payload["t"]) == len(payload["fut"]) == len(payload["max_pain"])

    async def test_a_capture_that_cannot_be_priced_is_none_not_zero(self) -> None:
        """Zero would drag the shared price scale to the floor and read as a
        crash that never happened."""
        service = _service([_snap(0, pain=24_600.0), _snap(30, pain=None, rows=())])

        payload = await service(TENANT, "NIFTY")

        assert payload["max_pain"][1] is None

    async def test_a_zero_stored_figure_is_treated_as_unpriced(self) -> None:
        service = _service([_snap(0, pain=24_600.0), _snap(30, pain=0.0, rows=())])

        payload = await service(TENANT, "NIFTY")

        assert payload["max_pain"][1] is None


class TestSpot:
    async def test_spot_comes_from_the_frames_not_the_live_chain(self) -> None:
        """Replaying an archived session must report where the index was *then*.

        The provider always answers with *today's* chain. Taking its spot
        unconditionally put this payload 950 points away from the profile panel
        on the very same page - two numbers for one instant, on one screen.
        """
        # The snapshots recorded 24,650; today's chain is 950 points away.
        service = _service(
            [_snap(0, pain=24_600.0), _snap(30, pain=24_650.0)],
            chain_rows=_ladder(24_700.0),
            chain_spot=25_600.0,
        )

        payload = await service(TENANT, "NIFTY")

        assert payload["spot"] == 24_650.0

    async def test_a_frame_with_no_spot_falls_through_to_the_chain(self) -> None:
        snaps = [
            ChainSnapshot(captured_at=BELL, rows=(_row("CE", 10),), max_pain=24_600.0),
            ChainSnapshot(
                captured_at=BELL + timedelta(minutes=30),
                rows=(_row("CE", 10),),
                max_pain=24_650.0,
            ),
        ]
        service = _service(snaps, chain_spot=25_600.0)

        payload = await service(TENANT, "NIFTY")

        assert payload["spot"] == 25_600.0


class TestReconstructedOpen:
    async def test_the_reconstructed_open_is_priced_rather_than_left_empty(self) -> None:
        """The hole this closes.

        ``session_open_frame`` carries rows but no header values, so its stored
        max pain is ``None``. Reading only the stored field would open the
        series with a gap at 09:15 - the one point a reader most wants, since
        the whole chart is about movement away from it.
        """
        late = datetime(2026, 8, 4, 6, 0, tzinfo=UTC)  # 11:30 IST, well past the bell
        snaps = [
            ChainSnapshot(
                captured_at=late,
                rows=_ladder(24_700.0),
                spot=24_650.0,
                max_pain=24_650.0,
                future_price=24_700.0,
            ),
            ChainSnapshot(
                captured_at=datetime(2026, 8, 4, 6, 30, tzinfo=UTC),
                rows=_ladder(24_700.0),
                spot=24_650.0,
                max_pain=24_650.0,
                future_price=24_710.0,
            ),
        ]
        service = _service(snaps)

        payload = await service(TENANT, "NIFTY")

        assert payload["open_is_estimated"] is True
        # Three points: the reconstructed open plus the two captures.
        assert len(payload["max_pain"]) == 3
        assert payload["max_pain"][0] is not None

    async def test_the_reconstructed_open_uses_the_same_formula_as_the_bar_chart(
        self,
    ) -> None:
        """Two panels on one page must never disagree about max pain."""
        rows = _ladder(24_600.0)
        late = datetime(2026, 8, 4, 6, 0, tzinfo=UTC)
        snaps = [
            ChainSnapshot(captured_at=late, rows=rows, spot=24_650.0, max_pain=24_600.0),
            ChainSnapshot(
                captured_at=datetime(2026, 8, 4, 6, 30, tzinfo=UTC),
                rows=rows,
                spot=24_650.0,
                max_pain=24_600.0,
            ),
        ]
        service = _service(snaps)

        payload = await service(TENANT, "NIFTY")

        expected = max_pain(rows, sorted({row.strike for row in rows}))
        assert payload["max_pain"][0] == expected


class TestDegradedTiers:
    async def test_an_unarchived_day_falls_to_a_two_point_proxy(self) -> None:
        """Honest, and labelled: the ingest worker has not run, so open-vs-now
        is genuinely all there is."""
        service = _service([], chain_rows=_ladder(24_700.0))

        payload = await service(TENANT, "NIFTY")

        assert payload["data_quality"] == "live_proxy"
        assert payload["open_is_estimated"] is True
        assert len(payload["t"]) == 2

    async def test_a_past_day_with_no_archive_is_empty_never_todays_chain(self) -> None:
        """Replaying an archived session must not quietly answer with today's
        live book - that would date a number to a day it never belonged to."""
        service = _service([], chain_rows=_ladder(24_700.0))

        payload = await service(
            TENANT, "NIFTY", trade_date=datetime(2026, 7, 30, 8, 0, tzinfo=UTC)
        )

        assert payload["data_quality"] == "empty"
        assert payload["t"] == []
        assert payload["max_pain"] == []

    async def test_an_empty_payload_is_still_well_formed(self) -> None:
        service = _service([])

        payload = await service(
            TENANT, "NIFTY", trade_date=datetime(2026, 7, 30, 8, 0, tzinfo=UTC)
        )

        assert payload["symbol"] == "NIFTY"
        assert payload["expiry_date"] == "2026-08-11"
        assert payload["open_ts"] and payload["now_ts"]
