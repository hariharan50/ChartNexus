"""The FYERS market-data provider.

Composes transport, quota, breaker, retry, and mappers into the
``MarketDataProvider`` port. Everything it returns is already canonical — no
FYERS vocabulary escapes this class.

It never falls back to synthetic data. When it cannot answer it raises, and the
application layer decides whether to serve cached data or mock, because only
that layer can label the result honestly.
"""

from __future__ import annotations

from typing import Protocol

from marketcompass.contexts.broker_connections.domain.value_objects import BrokerCredentials
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    DataSource,
    ExpiryList,
    FuturesQuote,
    OptionChain,
    Provenance,
    Quote,
)
from marketcompass.infrastructure.brokers.futures_contract import (
    resolve_front_month,
    to_futures_symbol,
)
from marketcompass.infrastructure.brokers.fyers import (
    futures_mapper,
    option_chain_mapper,
    quote_mapper,
)
from marketcompass.infrastructure.brokers.fyers.circuit_breaker import CircuitBreaker
from marketcompass.infrastructure.brokers.fyers.rest_client import FyersRestClient
from marketcompass.infrastructure.brokers.fyers.retry_policy import RetryPolicy, with_retry
from marketcompass.infrastructure.brokers.fyers.symbol_mapper import to_broker_symbol
from marketcompass.infrastructure.time.clock import SystemClock
from marketcompass.shared_kernel.domain.errors import UpstreamError

PROVIDER_NAME = "fyers"

# About twenty strikes either side of at-the-money — enough for max pain and
# gamma exposure without pulling the entire chain on every request.
DEFAULT_STRIKE_COUNT = 20


class QuotaManager(Protocol):
    async def acquire(self, app_id: str) -> None: ...


class FyersMarketDataProvider:
    """Implements the ``MarketDataProvider`` port."""

    def __init__(
        self,
        *,
        rest: FyersRestClient,
        credentials: BrokerCredentials,
        access_token: str,
        quota: QuotaManager,
        breaker: CircuitBreaker,
        retry: RetryPolicy | None = None,
        clock: SystemClock | None = None,
        strike_count: int = DEFAULT_STRIKE_COUNT,
    ) -> None:
        self._rest = rest
        self._credentials = credentials
        self._access_token = access_token
        self._quota = quota
        self._breaker = breaker
        self._retry = retry or RetryPolicy()
        self._clock = clock or SystemClock()
        self._strike_count = strike_count

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    async def get_quote(self, instrument: InstrumentSymbol) -> Quote:
        symbol = to_broker_symbol(instrument)
        await self._quota.acquire(self._credentials.app_id)

        payload = await self._guarded(
            lambda: self._rest.fetch_quotes(
                app_id=self._credentials.app_id,
                access_token=self._access_token,
                symbols=symbol,
            ),
            description=f"quotes:{instrument.value}",
        )
        return quote_mapper.to_quote(payload, instrument=instrument, fetched_at=self._clock.now())

    async def get_futures_quote(self, instrument: InstrumentSymbol) -> FuturesQuote:
        """The front-month future for an index.

        The active contract's month is taken from the broker's own expiry list
        (via the option chain) rather than a locally computed Thursday, so it is
        right across holidays and rolls the instant the near month expires. The
        contract price and day stats come from a direct quote on that symbol; if
        that quote is unavailable we degrade to the chain's futures reference
        price so a real number still reaches the card.
        """
        chain = await self.get_option_chain(instrument)
        contract_date = resolve_front_month(chain.expiries, self._clock.now().date())
        symbol = to_futures_symbol(instrument, contract_date)
        expiry_iso = contract_date.isoformat()

        try:
            await self._quota.acquire(self._credentials.app_id)
            payload = await self._guarded(
                lambda: self._rest.fetch_quotes(
                    app_id=self._credentials.app_id,
                    access_token=self._access_token,
                    symbols=symbol,
                ),
                description=f"futures:{instrument.value}",
            )
            return futures_mapper.to_futures_quote(
                payload,
                instrument=instrument,
                contract=symbol,
                expiry=expiry_iso,
                fetched_at=self._clock.now(),
            )
        except UpstreamError:
            if chain.future_price is None:
                raise
            return FuturesQuote(
                instrument=instrument,
                contract=symbol,
                expiry=expiry_iso,
                price=chain.future_price,
                change=None,
                change_percent=chain.change_percent,
                volume=0,
                day_high=None,
                day_low=None,
                provenance=Provenance(source=DataSource.LIVE, fetched_at=self._clock.now()),
            )

    async def get_option_chain(
        self, instrument: InstrumentSymbol, expiry: str | None = None
    ) -> OptionChain:
        symbol = to_broker_symbol(instrument)
        await self._quota.acquire(self._credentials.app_id)

        payload = await self._guarded(
            lambda: self._rest.fetch_option_chain(
                app_id=self._credentials.app_id,
                access_token=self._access_token,
                symbol=symbol,
                strike_count=self._strike_count,
            ),
            description=f"option-chain:{instrument.value}",
        )
        return option_chain_mapper.to_option_chain(
            payload,
            instrument=instrument,
            fetched_at=self._clock.now(),
            expiry=expiry,
        )

    async def get_expiries(self, instrument: InstrumentSymbol) -> ExpiryList:
        """Read expiries off the chain response.

        FYERS has no standalone expiry endpoint, and computing weekly expiries
        locally gets holidays wrong.
        """
        chain = await self.get_option_chain(instrument)
        return ExpiryList(
            instrument=instrument,
            expiries=chain.expiries or (chain.expiry,),
            provenance=Provenance(source=DataSource.LIVE, fetched_at=self._clock.now()),
        )

    async def _guarded(self, operation, *, description: str):  # type: ignore[no-untyped-def]
        """Breaker outside, retry inside.

        That order matters: retries happen only while the circuit is closed, so
        an outage costs one fast failure rather than three slow ones.
        """
        return await self._breaker.call(
            lambda: with_retry(operation, policy=self._retry, description=description)
        )
