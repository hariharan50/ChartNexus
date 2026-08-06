"""`GET /market/status`: the two exchange-local fields.

`time_ist` and `session_date` are named for the exchange's wall clock but are
built from a UTC-aware instant, so both need an explicit conversion. Without it
the dashboard badge reads 5h30m behind, and the session date rolls a day early
every evening after 18:30 IST — the second is the quieter failure, because it is
only wrong for six hours of the day and always agrees with UTC's own date.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from marketcompass.contexts.market_data.application.queries import GetMarketStatus
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    CandleInterval,
    CandleSeries,
    ExpiryList,
    FuturesQuote,
    OptionChain,
    Quote,
)
from marketcompass.infrastructure.time.clock import FixedClock
from marketcompass.infrastructure.time.market_calendar import ExchangeCalendar
from marketcompass.shared_kernel.types.identifiers import TenantId

pytestmark = pytest.mark.unit

TENANT = TenantId("00000000-0000-4000-8000-000000000001")


class _StubProvider:
    """Satisfies ``MarketDataProvider``; only ``name`` is read here."""

    name = "mock"

    async def get_spot(self, instrument: InstrumentSymbol) -> Quote:  # pragma: no cover
        raise NotImplementedError

    async def get_futures(self, instrument: InstrumentSymbol) -> FuturesQuote:  # pragma: no cover
        raise NotImplementedError

    async def get_option_chain(
        self, instrument: InstrumentSymbol, expiry: str | None = None
    ) -> OptionChain:  # pragma: no cover
        raise NotImplementedError

    async def get_expiries(self, instrument: InstrumentSymbol) -> ExpiryList:  # pragma: no cover
        raise NotImplementedError

    async def get_history(
        self, instrument: InstrumentSymbol, interval: CandleInterval, days: int
    ) -> CandleSeries:  # pragma: no cover
        raise NotImplementedError


class _StubResolver:
    async def resolve(self, tenant_id: TenantId) -> _StubProvider:
        return _StubProvider()


def _status_at(moment: datetime) -> GetMarketStatus:
    return GetMarketStatus(
        resolver=_StubResolver(),  # type: ignore[arg-type]
        clock=FixedClock(moment),
        calendar=ExchangeCalendar(),
    )


class TestMarketStatusClock:
    async def test_the_clock_is_ist_not_the_utc_instant_behind_it(self) -> None:
        # 17:21 UTC on a Thursday is 22:51 IST the same evening — the reading
        # that first showed up on the dashboard as "Delayed — 22:51:13" when it
        # was really a few minutes to 5pm IST.
        status = await _status_at(datetime(2026, 8, 6, 17, 21, 13, tzinfo=UTC))(TENANT)
        assert status.time_ist == "22:51:13"

    async def test_the_session_date_follows_ist_across_the_utc_midnight_gap(self) -> None:
        # 20:00 UTC is already 01:30 IST the next morning. Reading the date off
        # the UTC instant reports the session that has finished, not the one
        # about to start.
        status = await _status_at(datetime(2026, 8, 6, 20, 0, tzinfo=UTC))(TENANT)
        assert status.session_date == "2026-08-07"

    async def test_a_midday_session_is_reported_open(self) -> None:
        # 06:30 UTC == 12:00 IST on a Wednesday, mid-session.
        status = await _status_at(datetime(2026, 8, 5, 6, 30, tzinfo=UTC))(TENANT)
        assert status.is_open is True
        assert status.time_ist == "12:00:00"

    async def test_the_derivatives_close_runs_to_1540(self) -> None:
        # 15:35 IST is past the 15:30 cash close but inside the F&O session.
        status = await _status_at(datetime(2026, 8, 5, 10, 5, tzinfo=UTC))(TENANT)
        assert status.is_open is True
        assert status.market_close == "15:40"

    async def test_it_is_closed_once_the_derivatives_session_ends(self) -> None:
        # 15:41 IST.
        status = await _status_at(datetime(2026, 8, 5, 10, 11, tzinfo=UTC))(TENANT)
        assert status.is_open is False
