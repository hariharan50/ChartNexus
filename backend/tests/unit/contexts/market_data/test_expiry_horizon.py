"""The expiry list is capped to a trading horizon.

A broker will list monthlies a quarter out. Nobody reading an intraday options
tool trades those, and every extra entry is one more thing to scroll past in a
picker used constantly - so the list is trimmed once, here, where every caller
sees the same answer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from marketcompass.contexts.market_data.application.queries import (
    MAX_EXPIRY_HORIZON_DAYS,
    GetExpiries,
    QuoteQuery,
)
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    DataSource,
    ExpiryList,
    Provenance,
)
from marketcompass.shared_kernel.types.identifiers import TenantId

pytestmark = pytest.mark.unit

TENANT = TenantId(uuid.uuid4())
NOW = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
NIFTY = InstrumentSymbol("NIFTY")


class StubClock:
    def now(self) -> datetime:
        return NOW


class StubProvider:
    def __init__(self, expiries: tuple[str, ...]) -> None:
        self._expiries = expiries
        self.name = "stub"

    async def get_expiries(self, instrument: InstrumentSymbol) -> ExpiryList:
        return ExpiryList(
            instrument=instrument,
            expiries=self._expiries,
            provenance=Provenance(source=DataSource.LIVE, fetched_at=NOW),
        )


class StubResolver:
    def __init__(self, provider: StubProvider) -> None:
        self._provider = provider

    async def resolve(self, tenant_id: TenantId):  # type: ignore[no-untyped-def]
        return self._provider


def _service(expiries: tuple[str, ...]) -> GetExpiries:
    provider = StubProvider(expiries)
    return GetExpiries(resolver=StubResolver(provider), fallback=provider, clock=StubClock())


async def test_expiries_past_the_horizon_are_dropped() -> None:
    service = _service(
        ("2026-10-01", "2026-11-05", "2026-11-26", "2026-12-31", "2027-03-25")
    )

    result = await service(QuoteQuery(tenant_id=TENANT, instrument=NIFTY))

    # 2026-11-05 is exactly 42 days out; everything beyond it goes.
    assert result.expiries == ("2026-10-01", "2026-11-05")


async def test_the_horizon_day_itself_is_kept() -> None:
    horizon = "2026-11-05"
    service = _service(("2026-10-01", horizon))

    result = await service(QuoteQuery(tenant_id=TENANT, instrument=NIFTY))

    assert horizon in result.expiries
    assert MAX_EXPIRY_HORIZON_DAYS == 42


async def test_a_list_already_inside_the_horizon_is_untouched() -> None:
    expiries = ("2026-10-01", "2026-10-08", "2026-10-15")
    service = _service(expiries)

    result = await service(QuoteQuery(tenant_id=TENANT, instrument=NIFTY))

    assert result.expiries == expiries


async def test_the_nearest_expiry_survives_even_past_the_horizon() -> None:
    """A stock with monthly-only expiries can have nothing inside the window.

    Filtering naively would hand the picker an empty list and leave the page
    with no expiry to choose at all - worse than showing one that is far out.
    """
    service = _service(("2027-01-28", "2027-02-25"))

    result = await service(QuoteQuery(tenant_id=TENANT, instrument=NIFTY))

    assert result.expiries == ("2027-01-28",)


async def test_an_unparseable_date_is_kept_rather_than_silently_dropped() -> None:
    service = _service(("2026-10-01", "not-a-date"))

    result = await service(QuoteQuery(tenant_id=TENANT, instrument=NIFTY))

    assert "not-a-date" in result.expiries
