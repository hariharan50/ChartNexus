"""The FYERS market-data provider.

Composes transport, quota, breaker, retry, and mappers into the
``MarketDataProvider`` port. Everything it returns is already canonical — no
FYERS vocabulary escapes this class.

It never falls back to synthetic data. When it cannot answer it raises, and the
application layer decides whether to serve cached data or mock, because only
that layer can label the result honestly.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Protocol

from marketcompass.contexts.broker_connections.domain.value_objects import BrokerCredentials
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
    contract_for,
    resolve_front_month,
    to_futures_symbol,
)
from marketcompass.infrastructure.brokers.fyers import (
    futures_mapper,
    history_mapper,
    option_chain_mapper,
    quote_mapper,
)
from marketcompass.infrastructure.brokers.fyers.circuit_breaker import CircuitBreaker
from marketcompass.infrastructure.brokers.fyers.rest_client import (
    FyersRestClient,
    batch_symbols,
)
from marketcompass.infrastructure.brokers.fyers.retry_policy import RetryPolicy, with_retry
from marketcompass.infrastructure.brokers.fyers.symbol_mapper import to_broker_symbol
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.infrastructure.time.clock import SystemClock
from marketcompass.shared_kernel.domain.errors import UpstreamError, ValidationError

log = get_logger(__name__)

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

    async def get_futures_board(
        self, instruments: Sequence[InstrumentSymbol], *, series: int = 0
    ) -> dict[InstrumentSymbol, FuturesQuote]:
        """One futures series for many instruments, in batched requests.

        Two things make this affordable where calling ``get_futures_quote`` two
        hundred times would not:

        * the active contract is resolved from the calendar rather than from
          each instrument's expiry list, which removes one option-chain request
          per instrument; and
        * symbols are sent in batches of ``QUOTE_BATCH_SIZE``, turning
          ~220 requests into ~5.

        The calendar roll is the deliberate trade. ``resolve_front_month`` is
        more accurate because it reads the broker's own expiries and so handles
        a holiday-shifted expiry exactly; using it here would cost a request per
        instrument. For a board of day-change percentages, being on the wrong
        side of a roll for part of expiry day is a smaller error than not
        being able to draw the board at all — and the single-instrument path
        still uses the precise resolution.
        """
        today = self._clock.now().date()

        by_symbol: dict[str, InstrumentSymbol] = {}
        expiries: dict[InstrumentSymbol, str] = {}
        for instrument in instruments:
            try:
                # Per instrument: most share a monthly expiry, but nothing
                # guarantees it, and the catalog knows each one exactly.
                contract_date = contract_for(instrument, today, series)
                by_symbol[to_futures_symbol(instrument, contract_date)] = instrument
                expiries[instrument] = contract_date.isoformat()
            except ValidationError:
                # Not in the catalog, so there is no futures root to build a
                # symbol from. Skip it rather than failing the whole board.
                log.warning("futures_board_uncatalogued", symbol=instrument.value)

        board: dict[InstrumentSymbol, FuturesQuote] = {}
        for batch in batch_symbols(list(by_symbol)):
            try:
                await self._quota.acquire(self._credentials.app_id)
                payload = await self._guarded(
                    # Bind the batch per iteration: the lambda is called later,
                    # by the retry wrapper, and a free variable would resolve to
                    # whatever the loop had reached by then.
                    lambda batch=batch: self._rest.fetch_quotes(
                        app_id=self._credentials.app_id,
                        access_token=self._access_token,
                        symbols=batch,
                    ),
                    description=f"futures-board:{len(batch)}",
                )
            except Exception as exc:
                # One bad batch must not cost the other four. Logged, not
                # swallowed silently — a board quietly missing fifty rows is
                # indistinguishable from fifty contracts that did not trade.
                log.warning("futures_board_batch_failed", size=len(batch), error=repr(exc))
                continue

            fetched_at = self._clock.now()
            quotes = futures_mapper.split_quote_batch(payload)

            # Say what the broker actually sent when a quote cannot carry a
            # build-up read. Without this the board degrades to mock with
            # "broker_returned_nothing", which is true but says nothing about
            # *why* — and the answer is usually a field the payload omits.
            without_oi = [
                values
                for values in quotes.values()
                if futures_mapper.open_interest_of(values) is None
            ]
            if without_oi:
                log.warning(
                    "futures_board_quotes_without_open_interest",
                    missing=len(without_oi),
                    of=len(quotes),
                    available_fields=sorted(without_oi[0]),
                )

            for symbol, values in quotes.items():
                quoted = by_symbol.get(symbol)
                if quoted is None:
                    # The broker echoed something we did not ask for.
                    continue
                try:
                    board[quoted] = futures_mapper.to_futures_quote_from_values(
                        values,
                        instrument=quoted,
                        contract=symbol,
                        expiry=expiries.get(quoted, ""),
                        fetched_at=fetched_at,
                    )
                except UpstreamError:
                    # A contract with no price is not a quote. Leaving it out
                    # is how the board stays honest about what it knows.
                    continue

        return board

    async def get_open_interest(
        self, instrument: InstrumentSymbol, *, series: int = 0
    ) -> OpenInterestReading | None:
        """Open interest for one contract, from market depth.

        The catalog's listed expiries are used rather than the broker's own
        list for the same reason as the board: resolving each expiry from the
        broker costs an extra option-chain request per instrument, which is not
        affordable across a two-hundred-contract sweep.
        """
        contract = contract_for(instrument, self._clock.now().date(), series)
        symbol = to_futures_symbol(instrument, contract)

        await self._quota.acquire(self._credentials.app_id)
        payload = await self._guarded(
            lambda: self._rest.fetch_depth(
                app_id=self._credentials.app_id,
                access_token=self._access_token,
                symbol=symbol,
            ),
            description=f"depth:{instrument.value}",
        )
        return futures_mapper.to_open_interest(
            payload, instrument=instrument, symbol=symbol, observed_at=self._clock.now()
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

    async def get_history(
        self, instrument: InstrumentSymbol, interval: CandleInterval, days: int
    ) -> CandleSeries:
        symbol = to_broker_symbol(instrument)
        await self._quota.acquire(self._credentials.app_id)

        now = self._clock.now()
        # Inclusive on both ends, so `days=1` is today rather than nothing.
        range_from = (now.date() - timedelta(days=max(0, days - 1))).isoformat()

        payload = await self._guarded(
            lambda: self._rest.fetch_history(
                app_id=self._credentials.app_id,
                access_token=self._access_token,
                symbol=symbol,
                resolution=history_mapper.to_resolution(interval),
                range_from=range_from,
                range_to=now.date().isoformat(),
            ),
            description=f"history:{instrument.value}:{interval.value}",
        )
        return history_mapper.to_candle_series(
            payload, instrument=instrument, interval=interval, fetched_at=now
        )

    async def _guarded(self, operation, *, description: str):  # type: ignore[no-untyped-def]
        """Breaker outside, retry inside.

        That order matters: retries happen only while the circuit is closed, so
        an outage costs one fast failure rather than three slow ones.
        """
        return await self._breaker.call(
            lambda: with_retry(operation, policy=self._retry, description=description)
        )
