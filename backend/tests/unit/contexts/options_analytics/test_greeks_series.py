"""Intraday greeks behind the Option Greeks tool.

Two things would draw a confident wrong chart here, and both are pinned below: a
strike that rolls with the money while the title still names one contract, and a
leg the broker quoted no volatility on rendering as a real zero rather than a
gap. The maths itself is pinned against the textbook identities — put/call delta
parity, gamma and vega equality across the two sides — rather than against
numbers copied out of a terminal.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from chartnexus.contexts.options_analytics.application.greeks_series_service import (
    GetGreeksSeries,
    trading_symbol,
)
from chartnexus.contexts.options_analytics.application.ports import (
    ChainSnapshot,
    ProviderChain,
)
from chartnexus.contexts.options_analytics.domain.greeks_math import greeks, unit_vol
from chartnexus.contexts.options_analytics.domain.oi_math import ChainRow
from chartnexus.shared_kernel.types.identifiers import TenantId

pytestmark = pytest.mark.unit

TENANT = TenantId(uuid.uuid4())
# 08:00 UTC == 13:30 IST, inside the session on 2026-10-01.
NOW = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
#: 09:15 IST, the session bell, in UTC.
OPEN = datetime(2026, 10, 1, 3, 45, tzinfo=UTC)
EXPIRY = "2026-10-06"
SPOT = 22_400.0
LOT = 75


def _row(side: str, strike: float, *, ltp: float = 100.0, iv: float | None = 14.0) -> ChainRow:
    return ChainRow(
        strike=strike, option_type=side, oi=1_000, oi_change=0, ltp=ltp, volume=1, iv=iv
    )


def _ladder(*, iv: float | None = 14.0, centre: float = SPOT) -> tuple[ChainRow, ...]:
    """Five strikes either side of ``centre``, at 50-point spacing."""
    rows: list[ChainRow] = []
    for offset in range(-5, 6):
        strike = centre + 50.0 * offset
        rows.append(_row("CE", strike, iv=iv))
        rows.append(_row("PE", strike, iv=iv, ltp=90.0))
    return tuple(rows)


def _snap(
    minute: int,
    rows: tuple[ChainRow, ...],
    *,
    atm: float | None = SPOT,
    spot: float | None = SPOT,
) -> ChainSnapshot:
    return ChainSnapshot(
        captured_at=OPEN + timedelta(minutes=minute),
        rows=rows,
        expiry=EXPIRY,
        spot=spot,
        atm_strike=atm,
        future_price=spot,
    )


class StubProvider:
    def __init__(self, expiry: str | None = EXPIRY, rows: tuple[ChainRow, ...] = ()) -> None:
        self._expiry = expiry
        self._rows = rows

    async def fetch(
        self, tenant_id: TenantId, symbol: str, *, expiry: str | None = None
    ) -> ProviderChain:
        return ProviderChain(rows=self._rows, spot=SPOT, lot_size=LOT, expiry=self._expiry)


class StubReader:
    def __init__(self, snapshots: list[ChainSnapshot]) -> None:
        self._snapshots = snapshots

    async def latest_in_session(self, tenant_id, symbol, *, now_utc):  # type: ignore[no-untyped-def]
        return self._snapshots[-1] if self._snapshots else None

    async def day_snapshots(self, tenant_id, symbol, *, trade_date_utc):  # type: ignore[no-untyped-def]
        return list(self._snapshots)


def _service(
    snapshots: list[ChainSnapshot],
    *,
    chain_rows: tuple[ChainRow, ...] = (),
    expiry: str | None = EXPIRY,
) -> GetGreeksSeries:
    return GetGreeksSeries(
        provider=StubProvider(expiry, chain_rows),
        snapshots=StubReader(snapshots),
        now_utc=lambda: NOW,
    )


# -- the maths ---------------------------------------------------------------


def test_call_and_put_delta_satisfy_parity() -> None:
    """``delta_call - delta_put == 1`` for every undiscounted pair, by definition."""
    call = greeks(option_type="CE", spot=SPOT, strike=SPOT, years=0.02, vol=0.14)
    put = greeks(option_type="PE", spot=SPOT, strike=SPOT, years=0.02, vol=0.14)

    assert call.delta - put.delta == pytest.approx(1.0, abs=1e-9)
    assert 0.0 < call.delta < 1.0
    assert -1.0 < put.delta < 0.0


def test_gamma_and_vega_are_side_independent() -> None:
    call = greeks(option_type="CE", spot=SPOT, strike=SPOT, years=0.02, vol=0.14)
    put = greeks(option_type="PE", spot=SPOT, strike=SPOT, years=0.02, vol=0.14)

    assert call.gamma == pytest.approx(put.gamma, rel=1e-12)
    assert call.vega == pytest.approx(put.vega, rel=1e-12)
    assert call.gamma > 0.0
    assert call.vega > 0.0


def test_theta_is_a_daily_decay_not_an_annual_one() -> None:
    """The figure a reader expects next to a ₹100 option, not 365x it.

    An index ATM option a week out decays in the tens of rupees a day. Dividing
    the annual Black-Scholes theta by 365 is the whole difference between the
    reference terminal's -14.88 and a four-figure number nobody recognises.
    """
    call = greeks(option_type="CE", spot=SPOT, strike=SPOT, years=5 / 365, vol=0.14)

    assert call.theta < 0.0
    assert -60.0 < call.theta < -1.0


def test_a_degenerate_leg_is_zero_rather_than_nan() -> None:
    """Expiry day and an unquoted volatility are ordinary states of a live chain."""
    expired = greeks(option_type="CE", spot=SPOT, strike=SPOT, years=0.0, vol=0.14)
    unquoted = greeks(option_type="CE", spot=SPOT, strike=SPOT, years=0.02, vol=0.0)

    for result in (expired, unquoted):
        assert (result.delta, result.gamma, result.theta, result.vega) == (0.0, 0.0, 0.0, 0.0)
        assert not any(math.isnan(value) for value in (result.delta, result.gamma))


def test_unit_vol_converts_a_quoted_percentage() -> None:
    assert unit_vol(14.25) == pytest.approx(0.1425)
    assert unit_vol(None) == 0.0
    assert unit_vol(0.0) == 0.0


# -- the series --------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_session_is_read_at_one_pinned_strike() -> None:
    """The ATM drifts; the contract the chart is titled with must not.

    The later capture is at-the-money 100 points higher. A rolling read would
    switch contracts mid-line while the title still said 22400 — so the pin is
    taken from the latest capture and applied to the whole session.
    """
    snaps = [
        _snap(0, _ladder(), atm=SPOT),
        _snap(60, _ladder(), atm=SPOT + 100.0),
    ]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["strike"] == SPOT + 100.0
    assert payload["ce_symbol"] == "NIFTY06OCT2622500CE"
    assert payload["pe_symbol"] == "NIFTY06OCT2622500PE"
    assert len(payload["t"]) == 2
    assert payload["data_quality"] == "intraday"


@pytest.mark.asyncio
async def test_a_named_strike_overrides_the_money() -> None:
    payload = await _service([_snap(0, _ladder())])(TENANT, "NIFTY", strike=22_200.0)

    assert payload["strike"] == 22_200.0
    assert payload["ce_symbol"] == "NIFTY06OCT2622200CE"
    assert all(value is not None for value in payload["ce"]["delta"])


@pytest.mark.asyncio
async def test_an_unquoted_leg_reads_as_a_gap_not_a_zero() -> None:
    """A flat line through zero is a claim about the market. Absence is not."""
    snaps = [_snap(0, _ladder(iv=None)), _snap(30, _ladder())]

    payload = await _service(snaps)(TENANT, "NIFTY")

    assert payload["ce"]["delta"][0] is None
    assert payload["ce"]["iv"][0] is None
    assert payload["ce"]["delta"][1] is not None
    # Half the frames carried a usable volatility, and the payload says so.
    assert payload["iv_coverage"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_calls_and_puts_come_back_on_opposite_sides_of_zero() -> None:
    payload = await _service([_snap(0, _ladder())])(TENANT, "NIFTY")

    assert payload["ce"]["delta"][0] > 0.0
    assert payload["pe"]["delta"][0] < 0.0
    assert payload["ce"]["theta"][0] < 0.0
    assert payload["pe"]["theta"][0] < 0.0
    assert payload["ce"]["gamma"][0] > 0.0


@pytest.mark.asyncio
async def test_a_capture_that_lost_the_pinned_strike_is_dropped_not_bridged() -> None:
    """A ladder that drifted off the strike leaves a gap, not an invented point."""
    snaps = [
        _snap(0, _ladder()),
        _snap(30, _ladder(centre=SPOT + 1_000.0), atm=None, spot=SPOT + 1_000.0),
    ]

    payload = await _service(snaps)(TENANT, "NIFTY", strike=SPOT)

    assert len(payload["t"]) == 1


@pytest.mark.asyncio
async def test_a_day_with_no_archive_falls_back_to_one_live_point() -> None:
    """The ingest worker is a separate process; a machine without it still reads."""
    payload = await _service([], chain_rows=_ladder())(TENANT, "NIFTY")

    assert payload["data_quality"] == "live"
    assert len(payload["t"]) == 1
    assert payload["ce"]["delta"][0] is not None


@pytest.mark.asyncio
async def test_nothing_to_pin_is_an_empty_payload_not_a_crash() -> None:
    payload = await _service([])(TENANT, "NIFTY")

    assert payload["data_quality"] == "empty"
    assert payload["strike"] is None
    assert payload["t"] == []
    assert payload["ce"]["delta"] == []


@pytest.mark.asyncio
async def test_an_archive_of_another_expiry_is_not_drawn_under_this_title() -> None:
    """The archive holds whichever expiry the ingest worker was following."""
    other = ChainSnapshot(
        captured_at=OPEN + timedelta(minutes=10),
        rows=_ladder(),
        expiry="2026-10-27",
        spot=SPOT,
        atm_strike=SPOT,
    )

    payload = await _service([other], chain_rows=_ladder())(TENANT, "NIFTY")

    # Dropped to the live tier rather than relabelling the far contract's rows.
    assert payload["data_quality"] == "live"


def test_the_display_symbol_matches_the_exchange_spelling() -> None:
    assert trading_symbol("NIFTY", "2026-10-06", 22_400.0, "CE") == "NIFTY06OCT2622400CE"
    # Fractional strikes exist across the stock universe and must not render as
    # `2512.5` truncated to `2512`.
    assert trading_symbol("ABB", "2026-10-27", 2_512.5, "PE") == "ABB27OCT262512.5PE"
    assert trading_symbol("NIFTY", None, 22_400.0, "CE") is None
