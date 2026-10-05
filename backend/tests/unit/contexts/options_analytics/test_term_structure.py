"""The live volatility term structure.

The service exists because the archive cannot answer this question — it holds
one expiry per session — so every case here is about the live path: asking the
broker once per expiry, reading the money off each chain, and refusing to invent
a point for an expiry nobody priced.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from chartnexus.contexts.options_analytics.application.ports import ProviderChain
from chartnexus.contexts.options_analytics.application.term_structure_service import (
    MAX_EXPIRIES,
    GetTermStructure,
)
from chartnexus.contexts.options_analytics.domain.oi_math import ChainRow
from chartnexus.shared_kernel.types.identifiers import TenantId

TENANT = TenantId(uuid.uuid4())
# 08:00 UTC == 13:30 IST on 2026-09-03.
NOW = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
SPOT = 24_650.0


def _rows(*, atm_ce: float | None = 12.0, atm_pe: float | None = 14.0) -> tuple[ChainRow, ...]:
    """A ladder whose money sits at 24650."""
    out: list[ChainRow] = []
    for offset in (-1, 0, 1):
        strike = SPOT + 50.0 * offset
        at_money = offset == 0
        out.append(_row("CE", strike, atm_ce if at_money else 20.0))
        out.append(_row("PE", strike, atm_pe if at_money else 22.0))
    return tuple(out)


def _row(side: str, strike: float, iv: float | None) -> ChainRow:
    return ChainRow(strike=strike, option_type=side, oi=10, oi_change=0, ltp=5.0, volume=1, iv=iv)


class StubProvider:
    """Answers a different chain per expiry, and records what it was asked."""

    def __init__(self, by_expiry: dict[str, ProviderChain] | None = None) -> None:
        self._by_expiry = by_expiry or {}
        self.asked: list[str | None] = []

    async def fetch(self, tenant_id, symbol, *, expiry=None):  # type: ignore[no-untyped-def]
        self.asked.append(expiry)
        if expiry in self._by_expiry:
            return self._by_expiry[expiry]
        return ProviderChain(rows=_rows(), spot=SPOT, lot_size=75, expiry=expiry)


def _service(provider: StubProvider) -> GetTermStructure:
    return GetTermStructure(provider=provider, now_utc=lambda: NOW)


@pytest.mark.asyncio
async def test_reads_the_money_off_each_requested_expiry() -> None:
    provider = StubProvider()
    service = _service(provider)

    payload = await service(TENANT, "NIFTY", expiries=["2026-09-08", "2026-09-15"])

    assert provider.asked == ["2026-09-08", "2026-09-15"]
    assert [point["expiry"] for point in payload["points"]] == ["2026-09-08", "2026-09-15"]
    # Mean of the call and put at the money, not either alone.
    assert payload["points"][0]["atm_iv"] == pytest.approx(13.0)


@pytest.mark.asyncio
async def test_the_curve_is_ordered_by_expiry_not_by_the_order_asked_for() -> None:
    """A term structure is read left to right along the calendar."""
    service = _service(StubProvider())

    payload = await service(TENANT, "NIFTY", expiries=["2026-10-06", "2026-09-08"])

    assert [point["expiry"] for point in payload["points"]] == ["2026-09-08", "2026-10-06"]


@pytest.mark.asyncio
async def test_an_expiry_nobody_priced_has_no_point_rather_than_a_guess() -> None:
    """Interpolating from its neighbours would invent the number the reader came for."""
    blank = ProviderChain(
        rows=_rows(atm_ce=None, atm_pe=None), spot=SPOT, lot_size=75, expiry="2026-09-15"
    )
    service = _service(StubProvider({"2026-09-15": blank}))

    payload = await service(TENANT, "NIFTY", expiries=["2026-09-08", "2026-09-15"])

    by_expiry = {point["expiry"]: point["atm_iv"] for point in payload["points"]}
    assert by_expiry["2026-09-15"] is None
    assert by_expiry["2026-09-08"] is not None


@pytest.mark.asyncio
async def test_one_quoted_side_at_the_money_is_enough() -> None:
    half = ProviderChain(rows=_rows(atm_ce=None), spot=SPOT, lot_size=75, expiry="2026-09-08")
    service = _service(StubProvider({"2026-09-08": half}))

    payload = await service(TENANT, "NIFTY", expiries=["2026-09-08"])

    assert payload["points"][0]["atm_iv"] == pytest.approx(14.0)


@pytest.mark.asyncio
async def test_labels_the_point_with_what_the_broker_answered_not_what_was_asked() -> None:
    """A provider handed an expiry it does not list falls back to the nearest.

    Labelling the point with the request would quietly plot the same chain twice
    under two different dates.
    """
    fallback = ProviderChain(rows=_rows(), spot=SPOT, lot_size=75, expiry="2026-09-08")
    service = _service(StubProvider({"2030-01-01": fallback}))

    payload = await service(TENANT, "NIFTY", expiries=["2030-01-01"])

    assert payload["points"][0]["expiry"] == "2026-09-08"


@pytest.mark.asyncio
async def test_never_asks_the_broker_for_more_than_the_cap() -> None:
    provider = StubProvider()
    service = _service(provider)
    many = [f"2026-09-{day:02d}" for day in range(1, 12)]

    payload = await service(TENANT, "NIFTY", expiries=many)

    assert len(provider.asked) == MAX_EXPIRIES
    assert len(payload["points"]) == MAX_EXPIRIES


@pytest.mark.asyncio
async def test_a_repeated_expiry_costs_one_call_not_two() -> None:
    provider = StubProvider()
    service = _service(provider)

    payload = await service(TENANT, "NIFTY", expiries=["2026-09-08", "2026-09-08", " "])

    assert provider.asked == ["2026-09-08"]
    assert len(payload["points"]) == 1


@pytest.mark.asyncio
async def test_days_to_expiry_counts_from_the_ist_trading_date() -> None:
    service = _service(StubProvider())

    payload = await service(TENANT, "NIFTY", expiries=["2026-09-08"])

    # 3 Sep IST to 8 Sep.
    assert payload["points"][0]["days_to_expiry"] == 5


@pytest.mark.asyncio
async def test_an_expiry_already_past_reads_zero_rather_than_negative() -> None:
    service = _service(StubProvider())

    payload = await service(TENANT, "NIFTY", expiries=["2026-08-01"])

    assert payload["points"][0]["days_to_expiry"] == 0


@pytest.mark.asyncio
async def test_no_expiries_is_an_empty_curve_not_an_error() -> None:
    provider = StubProvider()
    service = _service(provider)

    payload = await service(TENANT, "NIFTY", expiries=[])

    assert payload["points"] == []
    assert provider.asked == []
    assert payload["symbol"] == "NIFTY"
