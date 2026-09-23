"""One strike's price/OI series behind the Price vs OI tool.

The cases pinned here are the ones that would draw a confident wrong chart: a
per-strike PCR dividing by no call interest, a half straddle from an unquoted
leg, and a fabricated opening bar on a thin day.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from marketcompass.contexts.options_analytics.application.ports import (
    ChainSnapshot,
    ProviderChain,
)
from marketcompass.contexts.options_analytics.application.strike_series_service import (
    GetStrikeSeries,
)
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


def _row(
    side: str,
    strike: float,
    *,
    ltp: float = 100.0,
    oi: int = 1_000,
    oi_change: int = 0,
) -> ChainRow:
    return ChainRow(
        strike=strike, option_type=side, oi=oi, oi_change=oi_change, ltp=ltp, volume=1, iv=14.0
    )


def _ladder(*extra: ChainRow) -> tuple[ChainRow, ...]:
    """Five strikes either side of 24650, plus any explicit rows for the strike
    under test (which override the filler at that strike)."""
    override_keys = {(row.strike, row.option_type) for row in extra}
    rows: list[ChainRow] = list(extra)
    for offset in range(-5, 6):
        strike = SPOT + 50.0 * offset
        for side in ("CE", "PE"):
            if (strike, side) not in override_keys:
                rows.append(_row(side, strike))
    return tuple(rows)


def _snap(minute: int, rows: tuple[ChainRow, ...], *, spot: float | None = SPOT) -> ChainSnapshot:
    return ChainSnapshot(
        captured_at=OPEN + timedelta(minutes=minute),
        rows=rows,
        spot=spot,
        atm_strike=SPOT,
        future_price=24_700.0,
    )


class StubProvider:
    def __init__(self, expiry: str | None = EXPIRY, spot: float | None = SPOT) -> None:
        self._expiry = expiry
        self._spot = spot

    async def fetch(self, tenant_id: TenantId, symbol: str) -> ProviderChain:
        return ProviderChain(rows=(), spot=self._spot, lot_size=LOT, expiry=self._expiry)


class StubReader:
    def __init__(self, snapshots: list[ChainSnapshot]) -> None:
        self._snapshots = snapshots

    async def latest_in_session(self, tenant_id, symbol, *, now_utc):  # type: ignore[no-untyped-def]
        return self._snapshots[-1] if self._snapshots else None

    async def day_snapshots(self, tenant_id, symbol, *, trade_date_utc):  # type: ignore[no-untyped-def]
        return list(self._snapshots)


def _service(
    snapshots: list[ChainSnapshot], *, provider: StubProvider | None = None
) -> GetStrikeSeries:
    return GetStrikeSeries(
        provider=provider or StubProvider(),
        snapshots=StubReader(snapshots),
        now_utc=lambda: NOW,
    )


# -- the payload ------------------------------------------------------------


async def test_all_arrays_share_the_time_axis_length() -> None:
    snaps = [_snap(0, _ladder()), _snap(30, _ladder())]

    payload = await _service(snaps)(TENANT, "NIFTY", strike=SPOT)

    width = len(payload["t"])
    assert width == 2
    for key in ("ce_price", "pe_price", "ce_oi", "pe_oi", "ce_oi_change", "pe_oi_change", "pcr"):
        assert len(payload[key]) == width
    assert payload["strike"] == SPOT
    assert SPOT in payload["strikes"]


async def test_the_selected_strikes_price_oi_and_straddle_flow_through() -> None:
    rows = _ladder(
        _row("CE", SPOT, ltp=120.0, oi=5_000, oi_change=500),
        _row("PE", SPOT, ltp=70.0, oi=8_000, oi_change=800),
    )
    payload = await _service([_snap(0, rows), _snap(30, rows)])(TENANT, "NIFTY", strike=SPOT)

    assert payload["ce_price"][-1] == 120.0
    assert payload["pe_price"][-1] == 70.0
    assert payload["ce_oi"][-1] == 5_000
    assert payload["pe_oi"][-1] == 8_000
    assert payload["ce_oi_change"][-1] == 500
    assert payload["pe_oi_change"][-1] == 800
    assert payload["straddle"][-1] == 190.0
    # PCR at the strike: put OI over call OI.
    assert payload["pcr"][-1] == 1.6


async def test_omitting_the_strike_lands_on_the_money() -> None:
    # Newest snapshot's ATM is 24650; omitting `strike` should plot it.
    rows = _ladder(_row("CE", SPOT, ltp=120.0), _row("PE", SPOT, ltp=70.0))
    payload = await _service([_snap(0, rows), _snap(30, rows)])(TENANT, "NIFTY")

    assert payload["strike"] == SPOT
    assert payload["ce_price"][-1] == 120.0
    assert payload["pe_price"][-1] == 70.0


async def test_pcr_is_none_not_zero_with_no_call_interest() -> None:
    rows = _ladder(
        _row("CE", SPOT, oi=0),
        _row("PE", SPOT, oi=8_000),
    )
    payload = await _service([_snap(0, rows), _snap(30, rows)])(TENANT, "NIFTY", strike=SPOT)

    assert payload["pcr"][-1] is None


async def test_straddle_is_none_when_a_leg_is_missing() -> None:
    # A capture that carried only the call at the strike — no put row.
    rows: tuple[ChainRow, ...] = (
        _row("CE", SPOT, ltp=120.0),
        *(_row(side, SPOT + 50.0 * o) for o in (1, 2) for side in ("CE", "PE")),
    )
    payload = await _service([_snap(0, rows), _snap(30, rows)])(TENANT, "NIFTY", strike=SPOT)

    assert payload["ce_price"][-1] == 120.0
    assert payload["pe_price"][-1] is None
    assert payload["straddle"][-1] is None


# -- degenerate days --------------------------------------------------------


async def test_an_empty_day_is_shaped_not_broken() -> None:
    payload = await _service([])(TENANT, "NIFTY", strike=SPOT)

    assert payload["data_quality"] == "empty"
    assert payload["t"] == []
    assert payload["strikes"] == []
    assert payload["strike"] == SPOT
    assert payload["expiry_date"] == EXPIRY


async def test_a_single_capture_is_not_a_session() -> None:
    payload = await _service([_snap(0, _ladder())])(TENANT, "NIFTY", strike=SPOT)

    assert payload["data_quality"] == "empty"


async def test_a_capture_with_no_spot_anywhere_is_dropped() -> None:
    blind = [
        ChainSnapshot(captured_at=OPEN, rows=_ladder(), spot=None, atm_strike=None),
        ChainSnapshot(
            captured_at=OPEN + timedelta(minutes=30), rows=_ladder(), spot=None, atm_strike=None
        ),
    ]
    payload = await _service(blind, provider=StubProvider(spot=None))(TENANT, "NIFTY", strike=SPOT)

    assert payload["data_quality"] == "empty"
    assert payload["t"] == []


# -- historical mode --------------------------------------------------------

# A past trading day; the stub reader ignores the date, so any past instant works.
PAST = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


async def test_historical_reads_the_archived_day() -> None:
    payload = await _service([_snap(0, _ladder()), _snap(30, _ladder())])(
        TENANT, "NIFTY", strike=SPOT, trade_date=PAST
    )

    assert payload["data_quality"] == "intraday"
    assert len(payload["t"]) == 2
