"""Per-strike vega exposure behind the Vega Analysis tool.

The cases pinned here are the ones that would draw a confident wrong chart: a
missing volatility silently priced as a real one, a synthetic future dragged to
the strike by an illiquid zero-priced leg, and a synthetic opening bar for a
market nobody observed.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta

from chartnexus.contexts.options_analytics.application.ports import (
    ChainSnapshot,
    ProviderChain,
)
from chartnexus.contexts.options_analytics.application.vega_series_service import GetVega
from chartnexus.contexts.options_analytics.domain.oi_math import ChainRow
from chartnexus.contexts.options_analytics.domain.vega_math import (
    bs_vega,
    leg_vega,
    synthetic_future,
    vega_profile,
)
from chartnexus.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())
# 08:00 UTC == 13:30 IST, inside the session on 2026-08-04.
NOW = datetime(2026, 8, 4, 8, 0, tzinfo=UTC)
EXPIRY = "2026-08-11"
SPOT = 24_650.0
LOT = 75


def _row(side: str, strike: float, oi: int, iv: float | None = 14.0, ltp: float = 10.0) -> ChainRow:
    return ChainRow(strike=strike, option_type=side, oi=oi, oi_change=0, ltp=ltp, volume=1, iv=iv)


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


def _service(snapshots: list[ChainSnapshot], *, expiry: str | None = EXPIRY) -> GetVega:
    return GetVega(
        provider=StubProvider(expiry),
        snapshots=StubReader(snapshots),
        now_utc=lambda: NOW,
    )


# -- the vega itself --------------------------------------------------------


def test_vega_peaks_at_the_money() -> None:
    at = bs_vega(spot=SPOT, strike=SPOT, years=0.02, rate=0.07, vol=0.14)
    above = bs_vega(spot=SPOT, strike=SPOT + 500, years=0.02, rate=0.07, vol=0.14)
    below = bs_vega(spot=SPOT, strike=SPOT - 500, years=0.02, rate=0.07, vol=0.14)

    assert at > above
    assert at > below


def test_vega_is_positive_for_a_live_leg() -> None:
    assert bs_vega(spot=SPOT, strike=SPOT, years=0.02, rate=0.07, vol=0.14) > 0.0


def test_vega_is_zero_rather_than_undefined_at_the_edges() -> None:
    """Expiry day and a missing volatility are ordinary states of a live chain.

    Both make d1 undefined. One bad leg must not take out the whole profile, so
    they return 0 rather than raising or propagating a NaN.
    """
    assert bs_vega(spot=SPOT, strike=SPOT, years=0.0, rate=0.07, vol=0.14) == 0.0
    assert bs_vega(spot=SPOT, strike=SPOT, years=0.02, rate=0.07, vol=0.0) == 0.0
    assert bs_vega(spot=0.0, strike=SPOT, years=0.02, rate=0.07, vol=0.14) == 0.0


def test_a_leg_is_vega_per_contract() -> None:
    # The definition, stated once so a refactor cannot quietly reintroduce a
    # spot^2 term and turn vega into gamma exposure, or a lot multiplier.
    assert leg_vega(vega=1.5, oi=1_000) == 1.5


def test_open_interest_does_not_scale_a_leg() -> None:
    """The regression this page was wrong on for its whole life.

    Weighting by open interest answers "how much money is exposed", not "how
    much volatility value is here" — and the two diverge violently. On 6 Oct
    2026 NIFTY put OI tripled between 09:15 and 11:38 while per-contract vega
    decayed to 0.79x, so the OI-weighted line climbed all morning on a day every
    option was *losing* vega. Every other terminal showed it falling.
    """
    quiet = leg_vega(vega=1.5, oi=1_000)
    crowded = leg_vega(vega=1.5, oi=50_000_000)

    assert quiet == crowded


# -- the profile ------------------------------------------------------------


def test_both_sides_are_positive() -> None:
    """A long option always has positive vega; the intraday delta carries sign."""
    axis = [SPOT - 50.0, SPOT, SPOT + 50.0]
    profile = vega_profile(_ladder(), spot=SPOT, years=0.02, axis=axis)

    assert all(entry.call_vega > 0.0 for entry in profile.strikes)
    assert all(entry.put_vega > 0.0 for entry in profile.strikes)


def test_a_leg_without_a_quoted_volatility_contributes_nothing() -> None:
    """Never a fallback volatility.

    A made-up 20% would produce a point indistinguishable from a real one. Zero
    plus a coverage figure lets the page say the number is missing.
    """
    axis = [SPOT]
    rows = (_row("CE", SPOT, 1_000, iv=None), _row("PE", SPOT, 1_000, iv=14.0))

    profile = vega_profile(rows, spot=SPOT, years=0.02, axis=axis)

    assert profile.strikes[0].call_vega == 0.0
    assert profile.strikes[0].put_vega > 0.0
    assert profile.iv_coverage == 0.5


def test_coverage_is_one_when_every_leg_is_priced() -> None:
    axis = [SPOT - 50.0, SPOT, SPOT + 50.0]

    profile = vega_profile(_ladder(), spot=SPOT, years=0.02, axis=axis)

    assert profile.iv_coverage == 1.0


def test_the_axis_is_honoured_even_where_the_chain_is_silent() -> None:
    # Frames share one axis, and the client indexes bars by position: a strike
    # the chain never quoted must still occupy its slot.
    axis = [SPOT - 50.0, SPOT, SPOT + 50.0, SPOT + 100.0]
    rows = (_row("CE", SPOT, 1_000), _row("PE", SPOT, 1_000))

    profile = vega_profile(rows, spot=SPOT, years=0.02, axis=axis)

    assert [entry.strike for entry in profile.strikes] == axis
    assert profile.strikes[3].call_vega == 0.0


# -- the synthetic future ---------------------------------------------------


def test_synthetic_future_is_call_minus_put_plus_strike() -> None:
    rows = (_row("CE", SPOT, 1_000, ltp=120.0), _row("PE", SPOT, 1_000, ltp=70.0))

    assert synthetic_future(rows, SPOT) == 120.0 - 70.0 + SPOT


def test_synthetic_future_needs_both_atm_legs() -> None:
    # An illiquid quote of 0.0 is treated as no leg, not a 0-priced option that
    # would drag the parity forward onto the strike itself.
    only_call = (_row("CE", SPOT, 1_000, ltp=120.0), _row("PE", SPOT, 1_000, ltp=0.0))

    assert synthetic_future(only_call, SPOT) is None
    assert synthetic_future((), SPOT) is None
    assert synthetic_future(only_call, None) is None


# -- the payload ------------------------------------------------------------


async def test_every_frame_shares_the_payloads_strike_axis() -> None:
    snaps = [_snap(0, _ladder()), _snap(30, _ladder())]

    payload = await _service(snaps)(TENANT, "NIFTY")

    width = len(payload["strikes"])
    assert width > 0
    for frame in payload["frames"]:
        assert len(frame["call_vega"]) == width
        assert len(frame["put_vega"]) == width


async def test_the_time_axis_matches_the_frames() -> None:
    snaps = [_snap(minute, _ladder()) for minute in (0, 15, 30)]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["t"] == [frame["t"] for frame in payload["frames"]]


async def test_the_synthetic_future_is_emitted_per_frame() -> None:
    rows = tuple(
        _row(side, strike, 1_000, ltp=(120.0 if side == "CE" else 70.0))
        if strike == SPOT
        else _row(side, strike, 1_000)
        for strike in (SPOT + 50.0 * offset for offset in range(-5, 6))
        for side in ("CE", "PE")
    )
    snaps = [_snap(0, rows), _snap(30, rows)]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["frames"][-1]["synth_future"] == round(120.0 - 70.0 + SPOT, 2)


async def test_synthetic_future_falls_back_to_the_tradable_future() -> None:
    # No ATM legs priced, so parity is undefined; the line falls back to the
    # snapshot's future rather than being left with a hole.
    zero_atm = tuple(
        _row(side, strike, 1_000, ltp=(0.0 if strike == SPOT else 10.0))
        for strike in (SPOT + 50.0 * offset for offset in range(-5, 6))
        for side in ("CE", "PE")
    )
    snaps = [_snap(0, zero_atm), _snap(30, zero_atm)]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["frames"][-1]["synth_future"] == 24_700.0


async def test_there_is_no_reconstructed_opening_frame() -> None:
    """Open interest can be restated from day-change; vega cannot.

    The reconstruction carries no spot, and vega is a function of where spot is.
    A synthetic 09:15 bar would be an invented number, so the series starts
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


async def test_coverage_travels_with_the_payload() -> None:
    snaps = [_snap(0, _ladder(iv=None)), _snap(30, _ladder(iv=None))]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["iv_coverage"] == 0.0
    assert all(value == 0.0 for value in payload["frames"][0]["call_vega"])


async def test_an_expired_chain_prices_to_zero_rather_than_raising() -> None:
    # Past the bell on expiry day there is no time value and no vega. The page
    # names this in its caption; the service must not produce a negative root.
    snaps = [_snap(0, _ladder()), _snap(30, _ladder())]

    payload = await _service(snaps, expiry="2026-08-03")(TENANT, "NIFTY")

    assert all(value == 0.0 for value in payload["frames"][-1]["call_vega"])


async def test_a_capture_with_no_spot_anywhere_is_dropped_not_zeroed() -> None:
    blind = [
        ChainSnapshot(captured_at=datetime(2026, 8, 4, 4, 0, tzinfo=UTC), rows=_ladder()),
        ChainSnapshot(captured_at=datetime(2026, 8, 4, 4, 30, tzinfo=UTC), rows=_ladder()),
    ]
    service = GetVega(
        provider=_SpotlessProvider(), snapshots=StubReader(blind), now_utc=lambda: NOW
    )

    payload = await service(TENANT, "NIFTY")

    assert payload["frames"] == []
    assert payload["data_quality"] == "empty"


class _SpotlessProvider:
    async def fetch(
        self, tenant_id: TenantId, symbol: str, *, expiry: str | None = None
    ) -> ProviderChain:
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


def test_values_are_finite_never_nan() -> None:
    axis = [SPOT - 50.0, SPOT, SPOT + 50.0]
    profile = vega_profile(_ladder(), spot=SPOT, years=0.02, axis=axis)

    assert all(math.isfinite(entry.call_vega) for entry in profile.strikes)
