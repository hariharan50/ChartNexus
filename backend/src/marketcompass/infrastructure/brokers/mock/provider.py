"""The mock market-data provider.

Serves generated data so the whole application runs with no broker account.
Every payload is stamped ``DataSource.MOCK`` — the one thing this provider must
never do is be mistaken for a real feed.
"""

from __future__ import annotations

from collections.abc import Sequence

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    CandleInterval,
    CandleSeries,
    DataSource,
    ExpiryList,
    FuturesQuote,
    OpenInterestReading,
    OptionChain,
    Provenance,
    Quote,
)
from marketcompass.infrastructure.brokers.futures_contract import (
    front_month_for,
    to_futures_symbol,
)
from marketcompass.infrastructure.brokers.mock.history_factory import build_history
from marketcompass.infrastructure.brokers.mock.option_chain_factory import (
    build_option_chain,
    upcoming_expiries,
)
from marketcompass.infrastructure.brokers.mock.quote_factory import (
    build_futures_quote,
    build_quote,
    in_ist,
    open_interest_at,
    previous_open_interest,
)
from marketcompass.infrastructure.time.clock import SystemClock
from marketcompass.shared_kernel.domain.errors import ValidationError

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

    async def get_futures_quote(self, instrument: InstrumentSymbol) -> FuturesQuote:
        now = self._clock.now()
        contract = front_month_for(instrument, now.date())
        return build_futures_quote(
            instrument, now, contract=to_futures_symbol(instrument, contract), expiry=contract
        )

    async def get_futures_board(
        self, instruments: Sequence[InstrumentSymbol]
    ) -> dict[InstrumentSymbol, FuturesQuote]:
        """The whole board, generated.

        No batching to do — there is no upstream to spare — but an instrument
        missing from the catalog is skipped rather than raised, matching the
        broker adapter's contract that a partial board beats a failed one.
        """
        now = self._clock.now()

        board: dict[InstrumentSymbol, FuturesQuote] = {}
        for instrument in instruments:
            try:
                # Resolved per instrument: most share a monthly expiry, but
                # nothing guarantees it and the catalog knows each exactly.
                contract = front_month_for(instrument, now.date())
                board[instrument] = build_futures_quote(
                    instrument,
                    now,
                    contract=to_futures_symbol(instrument, contract),
                    expiry=contract,
                )
            except ValidationError:
                continue
        return board

    async def get_open_interest(
        self, instrument: InstrumentSymbol
    ) -> OpenInterestReading | None:
        now = self._clock.now()
        try:
            return OpenInterestReading(
                instrument=instrument,
                open_interest=open_interest_at(instrument, now),
                previous_open_interest=previous_open_interest(instrument, in_ist(now).date()),
                observed_at=now,
            )
        except ValidationError:
            return None

    async def get_option_chain(
        self, instrument: InstrumentSymbol, expiry: str | None = None
    ) -> OptionChain:
        return build_option_chain(instrument, self._clock.now(), expiry)

    async def get_history(
        self, instrument: InstrumentSymbol, interval: CandleInterval, days: int
    ) -> CandleSeries:
        return build_history(instrument, interval, days, self._clock.now())

    async def get_expiries(self, instrument: InstrumentSymbol) -> ExpiryList:
        now = self._clock.now()
        return ExpiryList(
            instrument=instrument,
            expiries=upcoming_expiries(now.date()),
            provenance=Provenance(source=DataSource.MOCK, fetched_at=now),
        )
