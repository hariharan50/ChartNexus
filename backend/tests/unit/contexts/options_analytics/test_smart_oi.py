"""Per-bar OI flow behind the Smart OI page.

The page's whole claim is that a bar's histogram says what was written *during
that bar*. Every case pinned here is one where the obvious implementation
instead draws a level, a running total, or a confident zero — each of which
looks like a plausible chart and means something the market never did.

The two axes are the other recurring trap: the frame arrays and the bar arrays
have different lengths on purpose, and a test that zips them would pass by
accident on a fixture where the cadences happen to match.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from chartnexus.contexts.options_analytics.application.ports import (
    Candle,
    ChainSnapshot,
    ProviderChain,
)
from chartnexus.contexts.options_analytics.application.smart_oi_service import GetSmartOi
from chartnexus.contexts.options_analytics.domain.oi_math import ChainRow
from chartnexus.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())
# 08:00 UTC == 13:30 IST, inside the session on 2026-08-04.
NOW = datetime(2026, 8, 4, 8, 0, tzinfo=UTC)
# 09:15 IST, the bell.
OPEN = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)


def _row(
    side: str,
    *,
    oi: int = 0,
    change: int = 0,
    volume: int = 0,
    strike: float = 24_650.0,
) -> ChainRow:
    return ChainRow(
        strike=strike, option_type=side, oi=oi, oi_change=change, ltp=10.0, volume=volume, iv=None
    )


def _snap(minute: int, rows: tuple[ChainRow, ...], *, atm: float = 24_650.0) -> ChainSnapshot:
    # Anchored at the bell, so these fixtures get no reconstructed open — that
    # path has its own test, and a surprise extra frame at index 0 would make
    # every exact-array assertion here read as a failure of something else.
    return ChainSnapshot(
        captured_at=OPEN + _minutes(minute),
        rows=rows,
        spot=atm,
        atm_strike=atm,
        future_price=atm + 50,
    )


def _minutes(count: int) -> timedelta:
    return timedelta(minutes=count)


def _candle(minute: int, close: float = 24_650.0) -> Candle:
    return Candle(
        opened_at=OPEN + _minutes(minute),
        open=close - 5,
        high=close + 8,
        low=close - 9,
        close=close,
    )


class StubProvider:
    def __init__(self, rows: tuple[ChainRow, ...] = ()) -> None:
        self.rows = rows
        self.expiry_asked: str | None = None

    async def fetch(
        self, tenant_id: TenantId, symbol: str, *, expiry: str | None = None
    ) -> ProviderChain:
        self.expiry_asked = expiry
        return ProviderChain(
            rows=self.rows, spot=24_650.0, lot_size=75, expiry=expiry or "2026-08-11"
        )


class StubReader:
    def __init__(self, snapshots: list[ChainSnapshot]) -> None:
        self._snapshots = snapshots

    async def latest_in_session(self, tenant_id, symbol, *, now_utc):  # type: ignore[no-untyped-def]
        return self._snapshots[-1] if self._snapshots else None

    async def day_snapshots(self, tenant_id, symbol, *, trade_date_utc):  # type: ignore[no-untyped-def]
        return list(self._snapshots)


class StubCandles:
    def __init__(self, bars: list[Candle]) -> None:
        self._bars = bars

    async def minute_candles(self, tenant_id, symbol, *, trade_date_utc):  # type: ignore[no-untyped-def]
        return list(self._bars)


def _service(
    snapshots: list[ChainSnapshot],
    bars: list[Candle] | None = None,
    *,
    provider: StubProvider | None = None,
) -> GetSmartOi:
    return GetSmartOi(
        provider=provider or StubProvider(),
        snapshots=StubReader(snapshots),
        candles=StubCandles(bars if bars is not None else []),
        now_utc=lambda: NOW,
    )


# -- the flow, which is the page --------------------------------------------


async def test_smart_oi_is_the_flow_into_a_bar_not_the_level() -> None:
    """The histogram is the first difference of PE-CE, not PE-CE itself.

    Plotting the level draws a chart that only ever drifts one way and never
    prints a red bar all session — which is exactly the failure this page
    exists to avoid.
    """
    snaps = [
        _snap(0, (_row("CE", change=100), _row("PE", change=400))),  # PE-CE = 300
        _snap(1, (_row("CE", change=300), _row("PE", change=500))),  # PE-CE = 200
    ]
    view = await _service(snaps, [_candle(0), _candle(1)])(TENANT, "NIFTY", interval="1m")

    assert view["pe_ce_chg"] == [300, 200]
    # First bar carries the whole move off the 09:15 baseline of zero; the
    # second is the change *within* it, and it is negative.
    assert view["smart_oi"] == [300, -100]


async def test_a_bar_with_no_capture_is_null_not_zero() -> None:
    """A gap in the archive is an absence of observation, not an observation of nothing.

    Zero-height bars would claim the market went quiet in exactly the minutes
    the ingest worker happened to skip.
    """
    snaps = [_snap(0, (_row("PE", change=100),)), _snap(2, (_row("PE", change=250),))]
    view = await _service(snaps, [_candle(0), _candle(1), _candle(2)])(
        TENANT, "NIFTY", interval="1m"
    )

    assert view["smart_oi"] == [100, None, 150]


async def test_volume_bars_are_per_bar_not_cumulative() -> None:
    """Chain volume is cumulative from the bell, so the bars are its difference.

    Shipping the raw figure puts the day's running total in every bar and the
    pane grows monotonically all session regardless of activity.
    """
    snaps = [
        _snap(0, (_row("CE", volume=500), _row("PE", volume=300))),
        _snap(1, (_row("CE", volume=900), _row("PE", volume=1_000))),
    ]
    view = await _service(snaps, [_candle(0), _candle(1)])(TENANT, "NIFTY", interval="1m")

    assert view["call_vol"] == [500, 400]
    assert view["put_vol"] == [300, 700]


# -- the ratios -------------------------------------------------------------


async def test_both_ratios_are_puts_over_calls() -> None:
    snaps = [
        _snap(0, (_row("CE", oi=100, volume=50), _row("PE", oi=150, volume=200))),
        _snap(1, (_row("CE", oi=100, volume=50), _row("PE", oi=150, volume=200))),
    ]
    view = await _service(snaps)(TENANT, "NIFTY")

    assert view["oi_pcr"] == [1.5, 1.5]
    assert view["vol_pcr"] == [4.0, 4.0]


async def test_an_undefined_ratio_is_null_not_zero() -> None:
    """No denominator means no ratio.

    ``0`` draws a floor the market never printed and drags the axis down to it;
    ``None`` simply breaks the line, which is the honest rendering.
    """
    snaps = [
        _snap(0, (_row("PE", oi=150, volume=200),)),
        _snap(1, (_row("PE", oi=150, volume=200),)),
    ]
    view = await _service(snaps)(TENANT, "NIFTY")

    assert view["oi_pcr"] == [None, None]
    assert view["vol_pcr"] == [None, None]


# -- the strike window ------------------------------------------------------


async def test_strikes_outside_the_window_do_not_reach_the_totals() -> None:
    # A real ladder, so the 50-point step is inferable. With only two strikes
    # the "step" is the gap between them and every window contains everything —
    # which is the code behaving correctly on a fixture that is not a chain.
    rows = (
        _row("PE", change=1_000, strike=24_650.0),  # ATM
        _row("PE", change=1, strike=24_700.0),
        _row("PE", change=1, strike=24_750.0),
        _row("PE", change=9_999, strike=30_000.0),  # far wing
    )
    snaps = [_snap(0, rows), _snap(1, rows)]

    windowed = await _service(snaps)(TENANT, "NIFTY", span=1)
    whole = await _service(snaps)(TENANT, "NIFTY", span=None)

    assert windowed["put_oi_chg"] == [1_001, 1_001]
    assert whole["put_oi_chg"] == [11_001, 11_001]


async def test_auto_tracks_the_moving_atm_where_fixed_pins_to_the_open() -> None:
    """The two modes must genuinely differ on a trending day.

    ``auto`` keeps describing the money at play; ``fixed`` keeps describing the
    same ladder as it drifts out of the money. A page that silently switched
    between them would be neither.
    """
    # 100 everywhere except the strike the market trends *into*, so the two
    # modes cannot agree by coincidence.
    ladder = (
        _row("PE", change=100, strike=24_600.0),
        _row("PE", change=100, strike=24_650.0),
        _row("PE", change=100, strike=24_700.0),
        _row("PE", change=5_000, strike=24_750.0),
    )
    snaps = [
        _snap(0, ladder, atm=24_600.0),
        _snap(1, ladder, atm=24_700.0),
    ]

    auto = await _service(snaps)(TENANT, "NIFTY", mode="auto", span=1)
    fixed = await _service(snaps)(TENANT, "NIFTY", mode="fixed", span=1)

    # Auto re-centres: 24_550..24_650 at the open, then 24_650..24_750 — which
    # is where the writing went.
    assert auto["put_oi_chg"] == [200, 5_200]
    # Fixed stays on the open's window all session and never sees it.
    assert fixed["put_oi_chg"] == [200, 200]
    assert auto["strike_high"] == 24_750.0
    assert fixed["strike_high"] == 24_650.0


async def test_explicit_bounds_override_the_mode() -> None:
    rows = tuple(_row("PE", change=100, strike=strike) for strike in (24_000.0, 24_650.0, 25_000.0))
    snaps = [_snap(0, rows), _snap(1, rows)]

    view = await _service(snaps)(
        TENANT, "NIFTY", mode="auto", span=1, min_strike=24_000.0, max_strike=25_000.0
    )

    assert view["put_oi_chg"] == [300, 300]
    assert (view["strike_low"], view["strike_high"]) == (24_000.0, 25_000.0)


async def test_the_readout_reports_listed_strikes_not_the_arithmetic_bounds() -> None:
    """ "All" must read as the real ladder, not as ±infinity."""
    rows = tuple(_row("PE", oi=10, strike=strike) for strike in (24_000.0, 24_650.0, 25_000.0))
    view = await _service([_snap(0, rows), _snap(1, rows)])(TENANT, "NIFTY", span=None)

    assert (view["strike_low"], view["strike_high"]) == (24_000.0, 25_000.0)


# -- the candle grid --------------------------------------------------------


async def test_minute_bars_roll_up_into_the_requested_interval() -> None:
    """Open from the first minute, close from the last, extremes from all of them."""
    bars = [
        Candle(opened_at=OPEN, open=100, high=110, low=95, close=105),
        Candle(opened_at=OPEN + _minutes(1), open=105, high=130, low=104, close=120),
        Candle(opened_at=OPEN + _minutes(2), open=120, high=121, low=90, close=99),
        # A new 3m bucket starts at 09:18.
        Candle(opened_at=OPEN + _minutes(3), open=99, high=101, low=98, close=100),
    ]
    snaps = [_snap(0, (_row("PE", oi=1),)), _snap(1, (_row("PE", oi=1),))]
    view = await _service(snaps, bars)(TENANT, "NIFTY", interval="3m")

    assert len(view["bars"]) == 2
    first = view["bars"][0]
    assert (first["o"], first["h"], first["l"], first["c"]) == (100, 130, 90, 99)


async def test_bucket_boundaries_land_on_the_bell() -> None:
    """09:15 must open a bucket at every interval, or the first bar straddles it."""
    bars = [_candle(minute) for minute in range(30)]
    snaps = [_snap(0, (_row("PE", oi=1),)), _snap(1, (_row("PE", oi=1),))]

    for interval, size in (("1m", 1), ("3m", 3), ("5m", 5), ("15m", 15)):
        view = await _service(snaps, bars)(TENANT, "NIFTY", interval=interval)
        assert view["bars"][0]["t"] == OPEN.isoformat(), interval
        assert len(view["bars"]) == 30 // size, interval


async def test_the_two_axes_are_independent_lengths() -> None:
    """The frame arrays and the bar arrays describe different clocks."""
    snaps = [_snap(minute, (_row("PE", oi=minute + 1),)) for minute in range(7)]
    view = await _service(snaps, [_candle(minute) for minute in range(20)])(
        TENANT, "NIFTY", interval="5m"
    )

    frame_len = len(view["t"])
    bar_len = len(view["bars"])
    assert frame_len == 7
    assert bar_len == 4
    for key in ("fut", "call_oi_chg", "put_oi_chg", "pe_ce_chg", "oi_pcr", "vol_pcr"):
        assert len(view[key]) == frame_len, key
    for key in ("smart_oi", "call_vol", "put_vol"):
        assert len(view[key]) == bar_len, key


async def test_candles_still_draw_when_the_oi_tier_is_a_live_proxy() -> None:
    """The price pane comes from a different upstream and must not go blank with the archive."""
    provider = StubProvider(rows=(_row("CE", oi=100, change=10), _row("PE", oi=150, change=40)))
    view = await _service([], [_candle(minute) for minute in range(5)], provider=provider)(
        TENANT, "NIFTY", interval="1m"
    )

    assert view["data_quality"] == "live_proxy"
    assert len(view["bars"]) == 5


async def test_bars_that_have_not_opened_yet_are_dropped() -> None:
    """A seeded day can carry future bars; the chart must still stop at now."""
    future_minute = int((NOW - OPEN).total_seconds() // 60) + 10
    snaps = [_snap(0, (_row("PE", oi=1),)), _snap(1, (_row("PE", oi=1),))]
    view = await _service(snaps, [_candle(0), _candle(future_minute)])(
        TENANT, "NIFTY", interval="1m"
    )

    assert len(view["bars"]) == 1


# -- tiers and parameters ---------------------------------------------------


async def test_a_past_day_with_no_archive_is_empty_never_todays_chain() -> None:
    provider = StubProvider(rows=(_row("CE", oi=100), _row("PE", oi=150)))
    view = await _service([], [], provider=provider)(
        TENANT, "NIFTY", trade_date=datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    )

    assert view["data_quality"] == "empty"
    assert view["t"] == []
    assert view["oi_pcr"] == []


async def test_an_empty_day_still_ships_every_key_the_client_reads() -> None:
    """The empty tier is a shape, not an error — a missing key is a client crash."""
    view = await _service([], [])(
        TENANT, "NIFTY", trade_date=datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    )

    for key in ("t", "fut", "call_oi_chg", "put_oi_chg", "pe_ce_chg", "oi_pcr", "vol_pcr"):
        assert view[key] == [], key
    for key in ("bars", "smart_oi", "call_vol", "put_vol"):
        assert view[key] == [], key
    assert view["strike_low"] is None


async def test_the_requested_expiry_reaches_the_provider() -> None:
    provider = StubProvider()
    await _service([], [], provider=provider)(TENANT, "NIFTY", expiry="2026-09-29")

    assert provider.expiry_asked == "2026-09-29"


async def test_an_unknown_interval_falls_back_rather_than_raising() -> None:
    snaps = [_snap(0, (_row("PE", oi=1),)), _snap(1, (_row("PE", oi=1),))]
    view = await _service(snaps, [_candle(minute) for minute in range(10)])(
        TENANT, "NIFTY", interval="nonsense"
    )

    # 5m buckets, i.e. the default, applied to ten one-minute bars.
    assert len(view["bars"]) == 2


async def test_span_is_clamped_rather_than_trusted() -> None:
    rows = (_row("PE", change=100, strike=24_650.0),)
    snaps = [_snap(0, rows), _snap(1, rows)]

    view = await _service(snaps)(TENANT, "NIFTY", span=9_999)

    assert view["put_oi_chg"] == [100, 100]


async def test_the_reconstructed_open_anchors_the_first_bar() -> None:
    """A worker that started at 10:00 still measures flow from the bell.

    Without the reconstruction the baseline sits at 10:00 and every bar's
    "flow" is silently measured from mid-morning.
    """
    late = [
        _snap(45, (_row("CE", oi=500, change=100), _row("PE", oi=900, change=400))),
        _snap(46, (_row("CE", oi=500, change=100), _row("PE", oi=900, change=400))),
    ]
    view = await _service(late, [_candle(45)])(TENANT, "NIFTY", interval="1m")

    assert view["open_is_estimated"] is True
    # Index 0 is the reconstructed 09:15, where by definition nothing had moved.
    assert view["pe_ce_chg"][0] == 0
    assert view["t"][0] == OPEN.isoformat()
