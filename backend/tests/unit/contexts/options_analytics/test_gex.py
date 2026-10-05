"""Per-strike gamma exposure behind the Gamma Exposure tool.

The cases pinned here are the ones that would draw a confident wrong chart: a
missing volatility silently priced as a real one, a level rounded onto the wrong
side of spot, and a synthetic opening bar for a market nobody observed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from chartnexus.contexts.options_analytics.application.gex_service import GetGex
from chartnexus.contexts.options_analytics.application.ports import (
    ChainSnapshot,
    ProviderChain,
)
from chartnexus.contexts.options_analytics.domain.gex_math import (
    StrikeGex,
    bs_gamma,
    call_wall,
    leg_gex,
    net_cross,
    put_wall,
    strike_profile,
    zero_gamma,
)
from chartnexus.contexts.options_analytics.domain.oi_math import ChainRow
from chartnexus.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())
# 08:00 UTC == 13:30 IST, inside the session on 2026-08-04.
NOW = datetime(2026, 8, 4, 8, 0, tzinfo=UTC)
EXPIRY = "2026-08-11"
SPOT = 24_650.0
LOT = 75


def _row(side: str, strike: float, oi: int, iv: float | None = 14.0) -> ChainRow:
    return ChainRow(strike=strike, option_type=side, oi=oi, oi_change=0, ltp=10.0, volume=1, iv=iv)


def _ladder(
    *,
    call_oi: dict[float, int] | None = None,
    put_oi: dict[float, int] | None = None,
    iv: float | None = 14.0,
) -> tuple[ChainRow, ...]:
    """Five strikes either side of 24650, at 50-point spacing."""
    strikes = [SPOT + 50.0 * offset for offset in range(-5, 6)]
    calls = call_oi or {}
    puts = put_oi or {}
    rows: list[ChainRow] = []
    for strike in strikes:
        rows.append(_row("CE", strike, calls.get(strike, 1_000), iv))
        rows.append(_row("PE", strike, puts.get(strike, 1_000), iv))
    return tuple(rows)


#: 09:15 IST, the session bell, in UTC.
OPEN = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)


def _snap(minute: int, rows: tuple[ChainRow, ...], *, spot: float | None = SPOT) -> ChainSnapshot:
    return ChainSnapshot(
        captured_at=OPEN + timedelta(minutes=minute),
        rows=rows,
        spot=spot,
        atm_strike=SPOT,
        future_price=24_700.0,
    )


class StubProvider:
    def __init__(self, expiry: str | None = EXPIRY) -> None:
        self._expiry = expiry

    async def fetch(
        self, tenant_id: TenantId, symbol: str, *, expiry: str | None = None
    ) -> ProviderChain:
        return ProviderChain(rows=(), spot=SPOT, lot_size=LOT, expiry=self._expiry)


class StubReader:
    def __init__(self, snapshots: list[ChainSnapshot]) -> None:
        self._snapshots = snapshots

    async def latest_in_session(self, tenant_id, symbol, *, now_utc):  # type: ignore[no-untyped-def]
        return self._snapshots[-1] if self._snapshots else None

    async def day_snapshots(self, tenant_id, symbol, *, trade_date_utc):  # type: ignore[no-untyped-def]
        return list(self._snapshots)


def _service(snapshots: list[ChainSnapshot], *, expiry: str | None = EXPIRY) -> GetGex:
    return GetGex(
        provider=StubProvider(expiry),
        snapshots=StubReader(snapshots),
        now_utc=lambda: NOW,
    )


def _entries(nets: list[tuple[float, float]]) -> list[StrikeGex]:
    """Strikes carrying an exact net exposure, for testing the level scans."""
    return [
        StrikeGex(strike=strike, call_gex=max(0.0, net), put_gex=min(0.0, net))
        for strike, net in nets
    ]


# -- the gamma itself -------------------------------------------------------


def test_gamma_peaks_at_the_money() -> None:
    at = bs_gamma(spot=SPOT, strike=SPOT, years=0.02, rate=0.07, vol=0.14)
    above = bs_gamma(spot=SPOT, strike=SPOT + 500, years=0.02, rate=0.07, vol=0.14)
    below = bs_gamma(spot=SPOT, strike=SPOT - 500, years=0.02, rate=0.07, vol=0.14)

    assert at > above
    assert at > below


def test_gamma_is_zero_rather_than_undefined_at_the_edges() -> None:
    """Expiry day and a missing volatility are ordinary states of a live chain.

    Both make d1 undefined. One bad leg must not take out the whole profile, so
    they return 0 rather than raising or propagating a NaN.
    """
    assert bs_gamma(spot=SPOT, strike=SPOT, years=0.0, rate=0.07, vol=0.14) == 0.0
    assert bs_gamma(spot=SPOT, strike=SPOT, years=0.02, rate=0.07, vol=0.0) == 0.0
    assert bs_gamma(spot=0.0, strike=SPOT, years=0.02, rate=0.07, vol=0.14) == 0.0


def test_exposure_is_money_per_one_percent_move() -> None:
    # gamma * oi * spot^2 * 0.01 — the definition, stated once so a refactor
    # cannot quietly drop the 1% scaling and shift every figure by two orders of
    # magnitude, or reintroduce a lot multiplier over an OI already in units.
    value = leg_gex(gamma=0.0001, oi=1_000, spot=SPOT)

    assert value == 0.0001 * 1_000 * SPOT * SPOT * 0.01


# -- the profile ------------------------------------------------------------


def test_calls_are_positive_and_puts_negative() -> None:
    """The dealer convention: long calls, short puts.

    This is what makes the profile read green above spot and red below it. Flip
    it and the chart says the opposite of what it means.
    """
    axis = [SPOT - 50.0, SPOT, SPOT + 50.0]
    profile = strike_profile(_ladder(), spot=SPOT, years=0.02, axis=axis)

    assert all(entry.call_gex > 0.0 for entry in profile.strikes)
    assert all(entry.put_gex < 0.0 for entry in profile.strikes)


def test_a_leg_without_a_quoted_volatility_contributes_nothing() -> None:
    """Never a fallback volatility.

    A made-up 20% would produce a bar indistinguishable from a real one. Zero
    plus a coverage figure lets the page say the number is missing.
    """
    axis = [SPOT]
    rows = (_row("CE", SPOT, 1_000, iv=None), _row("PE", SPOT, 1_000, iv=14.0))

    profile = strike_profile(rows, spot=SPOT, years=0.02, axis=axis)

    assert profile.strikes[0].call_gex == 0.0
    assert profile.strikes[0].put_gex < 0.0
    assert profile.iv_coverage == 0.5


def test_coverage_is_one_when_every_leg_is_priced() -> None:
    axis = [SPOT - 50.0, SPOT, SPOT + 50.0]

    profile = strike_profile(_ladder(), spot=SPOT, years=0.02, axis=axis)

    assert profile.iv_coverage == 1.0


def test_coverage_ignores_unpriced_legs_that_nobody_holds() -> None:
    """Dead strikes must not raise the alarm.

    The IV solver fails on exactly the legs that carry no exposure — far-OTM
    strikes with no bid and no open interest. Counted by leg, a wall of those
    reported a fifth of the book missing on a profile whose every meaningful
    strike had priced, which is a false warning on the one caption a reader
    uses to decide whether to trust the figures.
    """
    axis = [SPOT, SPOT + 500.0]
    rows = (
        _row("CE", SPOT, 100_000),
        _row("PE", SPOT, 100_000),
        # Listed, quoted at nothing, held by nobody.
        _row("CE", SPOT + 500.0, 0, iv=None),
        _row("PE", SPOT + 500.0, 0, iv=None),
    )

    profile = strike_profile(rows, spot=SPOT, years=0.02, axis=axis)

    assert profile.iv_coverage == 1.0


def test_coverage_is_weighted_by_the_exposure_actually_missing() -> None:
    # One unpriced leg holding three quarters of the open interest is a real
    # hole, and has to read as one however few legs it is.
    axis = [SPOT, SPOT + 50.0]
    rows = (
        _row("CE", SPOT, 300_000, iv=None),
        _row("PE", SPOT, 100_000),
        _row("CE", SPOT + 50.0, 0),
        _row("PE", SPOT + 50.0, 0),
    )

    profile = strike_profile(rows, spot=SPOT, years=0.02, axis=axis)

    assert profile.iv_coverage == 0.25


def test_coverage_is_zero_on_an_axis_nobody_holds() -> None:
    # No exposure to have covered. Zero keeps the "cannot vouch for this"
    # reading, which is the right one for an axis of empty strikes.
    axis = [SPOT]
    rows = (_row("CE", SPOT, 0), _row("PE", SPOT, 0))

    assert strike_profile(rows, spot=SPOT, years=0.02, axis=axis).iv_coverage == 0.0


def test_abs_exposure_sees_a_strike_that_nets_to_zero() -> None:
    # A strike with equal call and put gamma is not a quiet strike, and the
    # net series alone would draw it as one.
    entry = StrikeGex(strike=SPOT, call_gex=5.0, put_gex=-5.0)

    assert entry.net == 0.0
    assert entry.abs == 10.0


def test_the_axis_is_honoured_even_where_the_chain_is_silent() -> None:
    # Frames share one axis, and the client indexes bars by position: a strike
    # the chain never quoted must still occupy its slot.
    axis = [SPOT - 50.0, SPOT, SPOT + 50.0, SPOT + 100.0]
    rows = (_row("CE", SPOT, 1_000), _row("PE", SPOT, 1_000))

    profile = strike_profile(rows, spot=SPOT, years=0.02, axis=axis)

    assert [entry.strike for entry in profile.strikes] == axis
    assert profile.strikes[3].call_gex == 0.0


# -- the four levels --------------------------------------------------------


def test_the_walls_land_on_the_heaviest_strike_on_each_side() -> None:
    axis = [SPOT + 50.0 * offset for offset in range(-5, 6)]
    rows = _ladder(call_oi={SPOT + 100.0: 90_000}, put_oi={SPOT - 100.0: 90_000})

    entries = strike_profile(rows, spot=SPOT, years=0.02, axis=axis).strikes

    assert call_wall(entries) == SPOT + 100.0
    assert put_wall(entries) == SPOT - 100.0


def test_a_one_sided_book_has_no_wall() -> None:
    # `None`, not 0 — a marker planted at the bottom of the ladder is worse
    # than no marker.
    entries = [StrikeGex(strike=SPOT, call_gex=0.0, put_gex=0.0)]

    assert call_wall(entries) is None
    assert put_wall(entries) is None


def test_the_flip_is_the_repriced_zero_gamma_level() -> None:
    """The flip is a re-priced price, not a strike read off today's profile.

    A book with the puts stacked below and the calls above is net short gamma
    low and net long gamma high, so re-pricing finds a zero-gamma level between
    the two — and, on a book symmetric about 24650, right at it. It is a price,
    not a listed strike, so bisection lands it off the grid.
    """
    axis = [SPOT + 50.0 * offset for offset in range(-5, 6)]
    rows = _ladder(
        call_oi={SPOT + 100.0: 90_000, SPOT + 150.0: 90_000},
        put_oi={SPOT - 100.0: 90_000, SPOT - 150.0: 90_000},
    )

    level = zero_gamma(rows, spot=SPOT, years=0.02, axis=axis)

    assert level is not None
    assert abs(level - SPOT) < 50.0


def test_a_one_sided_book_never_flips() -> None:
    # Calls only: net gamma is positive at every level and never crosses zero,
    # so there is no flip — `None`, not a marker planted at the edge.
    axis = [SPOT + 50.0 * offset for offset in range(-5, 6)]
    rows = tuple(_row("CE", strike, 1_000) for strike in axis)

    assert zero_gamma(rows, spot=SPOT, years=0.02, axis=axis) is None


def test_the_net_cross_takes_the_crossing_nearest_spot() -> None:
    """A noisy chain crosses zero out in the wings too.

    Only the crossing next to the money is a level anyone trades against, so
    "first found" is the wrong rule.
    """
    entries = _entries(
        [
            (24_300.0, -1.0),
            (24_350.0, 1.0),  # a wing crossing, far from spot
            (24_400.0, -1.0),
            (24_600.0, -1.0),
            (24_650.0, 1.0),  # the one that matters
        ]
    )

    level = net_cross(entries, SPOT)

    assert level is not None
    assert 24_600.0 < level <= 24_650.0


def test_the_flip_and_the_cross_are_different_levels() -> None:
    """They answer different questions and are drawn as separate markers.

    The flip is the re-priced level where the book as a whole turns net long
    gamma; the cross is where today's per-strike profile changes sign. On the
    same skewed book they land at different prices, and collapsing one into the
    other loses the distinction the page exists to show.
    """
    axis = [SPOT + 50.0 * offset for offset in range(-5, 6)]
    rows = _ladder(
        call_oi={SPOT + 100.0: 90_000, SPOT + 50.0: 60_000},
        put_oi={SPOT - 100.0: 150_000},
    )
    entries = strike_profile(rows, spot=SPOT, years=0.02, axis=axis).strikes

    flip = zero_gamma(rows, spot=SPOT, years=0.02, axis=axis)
    cross = net_cross(entries, SPOT)

    assert flip is not None
    assert cross is not None
    assert flip != cross


# -- the payload ------------------------------------------------------------


async def test_every_frame_shares_the_payloads_strike_axis() -> None:
    snaps = [_snap(0, _ladder()), _snap(30, _ladder())]

    payload = await _service(snaps)(TENANT, "NIFTY")

    width = len(payload["strikes"])
    assert width > 0
    for frame in payload["frames"]:
        assert len(frame["call_gex"]) == width
        assert len(frame["put_gex"]) == width


async def test_the_time_axis_matches_the_frames() -> None:
    snaps = [_snap(minute, _ladder()) for minute in (0, 15, 30)]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["t"] == [frame["t"] for frame in payload["frames"]]


async def test_the_levels_are_recomputed_per_frame() -> None:
    # Positioning moves through the session; a payload-level wall would show
    # this morning's structure against this afternoon's bars.
    morning = _snap(0, _ladder(call_oi={SPOT + 100.0: 90_000}))
    afternoon = _snap(240, _ladder(call_oi={SPOT + 250.0: 90_000}))

    payload = await _service([morning, afternoon])(TENANT, "NIFTY")

    assert payload["frames"][0]["call_wall"] == SPOT + 100.0
    assert payload["frames"][1]["call_wall"] == SPOT + 250.0


async def test_there_is_no_reconstructed_opening_frame() -> None:
    """Open interest can be restated from day-change; gamma cannot.

    The reconstruction carries no spot, and gamma is a function of where spot
    is. A synthetic 09:15 bar would be an invented number, so the series starts
    where the recording does — here 10:30, not the bell.
    """
    late = ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 5, 0, tzinfo=UTC),
        rows=_ladder(),
        spot=SPOT,
        atm_strike=SPOT,
    )
    later = ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 5, 30, tzinfo=UTC),
        rows=_ladder(),
        spot=SPOT,
        atm_strike=SPOT,
    )

    payload = await _service([late, later])(TENANT, "NIFTY")

    assert payload["open_is_estimated"] is False
    assert len(payload["frames"]) == 2
    assert payload["open_ts"] == datetime(2026, 8, 4, 5, 0, tzinfo=UTC).isoformat()


async def test_a_capture_falls_back_through_atm_then_the_live_chain() -> None:
    # A capture taken before the spot column was denormalised still has an ATM
    # strike, and the live chain has a level of its own. Both are close enough
    # to place gamma, so a frame is only ever dropped when all three are gone.
    no_spot = ChainSnapshot(
        captured_at=datetime(2026, 8, 4, 4, 0, tzinfo=UTC), rows=_ladder(), atm_strike=SPOT
    )
    bare = ChainSnapshot(captured_at=datetime(2026, 8, 4, 4, 30, tzinfo=UTC), rows=_ladder())

    payload = await _service([no_spot, bare])(TENANT, "NIFTY")

    assert [frame["spot"] for frame in payload["frames"]] == [SPOT, SPOT]


async def test_a_capture_with_no_spot_anywhere_is_dropped_not_zeroed() -> None:
    """Gamma has to be placed somewhere.

    A frame of zeros would draw a flat market that never happened; a gap in the
    timeline is what a gap is.
    """
    blind = [
        ChainSnapshot(captured_at=datetime(2026, 8, 4, 4, 0, tzinfo=UTC), rows=_ladder()),
        ChainSnapshot(captured_at=datetime(2026, 8, 4, 4, 30, tzinfo=UTC), rows=_ladder()),
    ]
    service = GetGex(provider=_SpotlessProvider(), snapshots=StubReader(blind), now_utc=lambda: NOW)

    payload = await service(TENANT, "NIFTY")

    assert payload["frames"] == []
    assert payload["data_quality"] == "empty"


async def test_coverage_travels_with_the_payload() -> None:
    snaps = [_snap(0, _ladder(iv=None)), _snap(30, _ladder(iv=None))]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["iv_coverage"] == 0.0
    assert all(value == 0.0 for value in payload["frames"][0]["call_gex"])


async def test_an_expired_chain_prices_to_zero_rather_than_raising() -> None:
    # Past the bell on expiry day there is no time value and no gamma. The page
    # names this in its caption; the service must not produce a negative root.
    snaps = [_snap(0, _ladder()), _snap(30, _ladder())]

    payload = await _service(snaps, expiry="2026-08-03")(TENANT, "NIFTY")

    assert payload["frames"][-1]["net_total"] == 0.0


async def test_an_unknown_expiry_does_not_invent_one() -> None:
    snaps = [_snap(0, _ladder()), _snap(30, _ladder())]

    payload = await _service(snaps, expiry=None)(TENANT, "NIFTY")

    assert payload["expiry_date"] is None
    assert payload["frames"][-1]["abs_total"] == 0.0


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


class _SpotlessProvider:
    async def fetch(
        self, tenant_id: TenantId, symbol: str, *, expiry: str | None = None
    ) -> ProviderChain:
        return ProviderChain(rows=(), spot=None, lot_size=LOT, expiry=EXPIRY)


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
