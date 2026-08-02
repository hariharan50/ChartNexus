"""The mock market-data provider.

Serves generated data so the whole application runs with no broker account.
Every payload is stamped ``DataSource.MOCK`` — the one thing this provider must
never do is be mistaken for a real feed.
"""

from __future__ import annotations

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    DataSource,
    ExpiryList,
    OptionChain,
    Provenance,
    Quote,
)
from marketcompass.infrastructure.brokers.mock.option_chain_factory import (
    build_option_chain,
    upcoming_expiries,
)
from marketcompass.infrastructure.brokers.mock.quote_factory import build_quote
from marketcompass.infrastructure.time.clock import SystemClock

PROVIDER_NAME = "mock"


class MockMarketDataProvider:
    """Implements the ``MarketDataProvider`` port."""

    def __init__(self, clock: SystemClock | None = None) -> None:
        self._clock = clock or SystemClock()

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    async def get_quote(self, instrument: InstrumentSymbol) -> Quote:
        return build_quote(instrument, self._clock.now())

    async def get_option_chain(
        self, instrument: InstrumentSymbol, expiry: str | None = None
    ) -> OptionChain:
        return build_option_chain(instrument, self._clock.now(), expiry)

    async def get_expiries(self, instrument: InstrumentSymbol) -> ExpiryList:
        now = self._clock.now()
        return ExpiryList(
            instrument=instrument,
            expiries=upcoming_expiries(now.date()),
            provenance=Provenance(source=DataSource.MOCK, fetched_at=now),
        )
