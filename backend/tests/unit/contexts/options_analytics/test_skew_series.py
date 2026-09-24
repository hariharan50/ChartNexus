"""Per-strike implied volatility and open interest behind the Volatility Skew tool.

The service computes nothing — it projects what the chain quoted onto a shared
axis — so what is worth pinning is everything that could silently invent a
number: a missing volatility coerced to zero, a frame drawn without a spot to
put the money at, and a coverage figure that would let an unpriced chain pass
for a flat one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from marketcompass.contexts.options_analytics.application.ports import (
    ChainSnapshot,
    ProviderChain,
)
from marketcompass.contexts.options_analytics.application.skew_series_service import GetSkew
from marketcompass.contexts.options_analytics.domain.oi_math import ChainRow
from marketcompass.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())
# 08:00 UTC == 13:30 IST, inside the session on 2026-08-04.
NOW = datetime(2026, 8, 4, 8, 0, tzinfo=UTC)
EXPIRY = "2026-08-11"
SPOT = 24_650.0
LOT = 75
#: 09:15 IST, the session bell, in UTC.
OPEN = datetime(2026, 8, 4, 3, 45, tzinfo=UTC)


def _row(side: str, strike: float, oi: int, iv: float | None = 14.0) -> ChainRow:
    return ChainRow(strike=strike, option_type=side, oi=oi, oi_change=0, ltp=10.0, volume=1, iv=iv)


def _ladder(
    *,
    call_iv: dict[float, float | None] | None = None,
    put_iv: dict[float, float | None] | None = None,
    call_oi: dict[float, int] | None = None,
    put_oi: dict[float, int] | None = None,
) -> tuple[ChainRow, ...]:
    """Two strikes either side of 24650, at 50-point spacing."""
    rows: list[ChainRow] = []
    for strike in _strikes():
        rows.append(
            _row(
                "CE", strike, (call_oi or {}).get(strike, 1_000), (call_iv or {}).get(strike, 14.0)
            )
        )
        rows.append(
            _row("PE", strike, (put_oi or {}).get(strike, 2_000), (put_iv or {}).get(strike, 16.0))
        )
    return tuple(rows)


def _strikes() -> list[float]:
    return [SPOT + 50.0 * offset for offset in range(-2, 3)]


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


def _service(snapshots: list[ChainSnapshot], *, expiry: str | None = EXPIRY) -> GetSkew:
    return GetSkew(
        provider=StubProvider(expiry),
        snapshots=StubReader(snapshots),
        now_utc=lambda: NOW,
    )


# -- the projection ---------------------------------------------------------


@pytest.mark.asyncio
async def test_every_frame_carries_both_sides_aligned_to_the_shared_axis() -> None:
    service = _service([_snap(0, _ladder()), _snap(30, _ladder())])

    payload = await service(TENANT, "NIFTY")

    assert payload["data_quality"] == "intraday"
    assert payload["strikes"] == _strikes()
    assert len(payload["frames"]) == 2
    for frame in payload["frames"]:
        for key in ("ce_iv", "pe_iv", "call_oi", "put_oi"):
            assert len(frame[key]) == len(payload["strikes"])


@pytest.mark.asyncio
async def test_the_two_sides_keep_their_own_volatility() -> None:
    """The whole page is the gap between them — they must not be averaged here."""
    service = _service([_snap(0, _ladder()), _snap(30, _ladder())])

    frame = (await service(TENANT, "NIFTY"))["frames"][-1]

    assert frame["ce_iv"] == [14.0] * 5
    assert frame["pe_iv"] == [16.0] * 5


@pytest.mark.asyncio
async def test_each_frame_carries_the_tradable_future() -> None:
    """The IV Intraday page draws volatility against price from this one payload."""
    service = _service([_snap(0, _ladder()), _snap(30, _ladder())])

    frame = (await service(TENANT, "NIFTY"))["frames"][-1]

    assert frame["future"] == 24_700.0


@pytest.mark.asyncio
async def test_the_future_falls_back_to_spot_on_a_capture_that_recorded_none() -> None:
    older = ChainSnapshot(
        captured_at=OPEN + timedelta(minutes=15), rows=_ladder(), spot=SPOT, atm_strike=SPOT
    )
    service = _service([_snap(0, _ladder()), older, _snap(30, _ladder())])

    payload = await service(TENANT, "NIFTY")
    middle = payload["frames"][1]

    assert middle["future"] == SPOT


@pytest.mark.asyncio
async def test_an_unquoted_volatility_stays_null_rather_than_zero() -> None:
    """Zero is a real volatility, and a false one. The curve must break instead."""
    rows = _ladder(call_iv={SPOT: None})
    service = _service([_snap(0, rows), _snap(30, rows)])

    frame = (await service(TENANT, "NIFTY"))["frames"][-1]

    assert frame["ce_iv"][_strikes().index(SPOT)] is None
    assert 0.0 not in frame["ce_iv"]


@pytest.mark.asyncio
async def test_open_interest_on_a_strike_nobody_quoted_is_zero_not_null() -> None:
    """Unlike volatility: a leg nobody quoted holds no position, and that is a fact."""
    rows = tuple(row for row in _ladder() if not (row.option_type == "CE" and row.strike == SPOT))
    service = _service([_snap(0, rows), _snap(30, rows)])

    payload = await service(TENANT, "NIFTY")
    frame = payload["frames"][-1]
    index = payload["strikes"].index(SPOT)

    assert frame["call_oi"][index] == 0
    assert frame["ce_iv"][index] is None


@pytest.mark.asyncio
async def test_coverage_reports_the_share_of_legs_that_carried_a_volatility() -> None:
    # One call leg of ten is unpriced.
    rows = _ladder(call_iv={SPOT: None})
    service = _service([_snap(0, rows), _snap(30, rows)])

    payload = await service(TENANT, "NIFTY")

    assert payload["iv_coverage"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_a_chain_with_no_volatility_at_all_is_visibly_uncovered() -> None:
    """The page needs to tell "no skew" from "no data" — coverage is how."""
    rows = _ladder(
        call_iv=dict.fromkeys(_strikes()),
        put_iv=dict.fromkeys(_strikes()),
    )
    service = _service([_snap(0, rows), _snap(30, rows)])

    payload = await service(TENANT, "NIFTY")

    assert payload["iv_coverage"] == 0.0
    assert payload["frames"][-1]["ce_iv"] == [None] * 5


# -- frames that cannot be drawn -------------------------------------------


@pytest.mark.asyncio
async def test_a_capture_with_no_spot_is_dropped_rather_than_drawn() -> None:
    """Which side of the money a strike is on decides which leg's IV the curve
    takes. Without spot there is no money to be on."""
    spotless = ChainSnapshot(
        captured_at=OPEN + timedelta(minutes=15), rows=_ladder(), spot=None, atm_strike=None
    )
    service = _service([_snap(0, _ladder()), spotless, _snap(30, _ladder())])

    payload = await service(TENANT, "NIFTY")

    assert len(payload["frames"]) == 2
    assert len(payload["t"]) == 2


@pytest.mark.asyncio
async def test_a_thin_day_is_empty_not_proxied_from_the_live_chain() -> None:
    service = _service([_snap(0, _ladder())])

    payload = await service(TENANT, "NIFTY")

    assert payload["data_quality"] == "empty"
    assert payload["frames"] == []
    assert payload["strikes"] == []
    # Still a well-formed header, so the page renders its empty state.
    assert payload["symbol"] == "NIFTY"
    assert payload["expiry_date"] == EXPIRY
    assert payload["lot_size"] == LOT


@pytest.mark.asyncio
async def test_historical_with_no_archive_is_empty_not_live() -> None:
    service = _service([])

    payload = await service(TENANT, "NIFTY", trade_date=datetime(2026, 7, 30, 8, 0, tzinfo=UTC))

    assert payload["data_quality"] == "empty"


# -- the axis ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_axis_is_bounded_around_the_money() -> None:
    """A ladder that drifts all session must not grow the payload without bound."""
    far = (*_ladder(), _row("CE", 40_000.0, 5), _row("PE", 40_000.0, 5))
    service = _service([_snap(0, far), _snap(30, _ladder())])

    payload = await service(TENANT, "NIFTY")

    assert 40_000.0 not in payload["strikes"]
    assert payload["strikes"] == _strikes()


@pytest.mark.asyncio
async def test_the_axis_keeps_every_strike_the_newest_capture_quotes() -> None:
    """The window is a bound on drift, not on the chain the reader is looking at."""
    service = _service([_snap(0, _ladder()), _snap(30, _ladder())], expiry=None)

    payload = await service(TENANT, "NIFTY")

    assert payload["strikes"] == _strikes()
    assert payload["atm_strike"] == SPOT
