"""The Kite Connect market-data provider.

Implements ``MarketDataProvider`` over Kite's ``/quote``, historical and
instrument-dump endpoints. Everything it returns is canonical; no Kite
vocabulary escapes.

Same contract as the FYERS provider: it never falls back to synthetic data.
When it cannot answer it raises ``UpstreamError`` and the application layer's
ladder (``live → last-good → mock``) decides what to serve, labelled.

Where Kite differs and this class leans on it:

* **OI in quotes.** Futures and options carry ``oi`` in the ordinary quote, so
  the futures board's OI comes with its prices — one request where FYERS needs
  a depth call per contract.
* **No option-chain endpoint.** Chains are composed from the instrument
  catalog plus one batched quote (≤ 500 instruments).
* **One quote request per second.** Every quote goes through
  :class:`~.quote_cache.KiteQuoteCache`, which answers repeat questions from a
  1.5 s cache and batches everything recently asked about into each request.
* **Expiry is honoured.** Contracts are named by date in the catalog, so a
  requested expiry is fetched exactly — unlike the FYERS chain endpoint.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from chartnexus.contexts.broker_connections.domain.errors import (
    BrokerRejectedError,
    BrokerUnavailableError,
)
from chartnexus.contexts.broker_connections.domain.value_objects import BrokerCredentials
from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import (
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
from chartnexus.infrastructure.brokers.fyers.circuit_breaker import CircuitBreaker
from chartnexus.infrastructure.brokers.fyers.retry_policy import RetryPolicy, with_retry
from chartnexus.infrastructure.brokers.kite import mappers
from chartnexus.infrastructure.brokers.kite.catalog import KiteInstrumentIndex
from chartnexus.infrastructure.brokers.kite.instruments import INDEX_SPOTS, KiteInstrument, spot_key
from chartnexus.infrastructure.brokers.kite.prev_oi import PreviousOpenInterest
from chartnexus.infrastructure.brokers.kite.quote_cache import KiteQuoteCache
from chartnexus.infrastructure.brokers.kite.rest_client import (
    BROKER,
    QUOTE_BATCH_LIMIT,
    KiteRestClient,
)
from chartnexus.infrastructure.brokers.quota import NullBucketQuota, RedisBucketQuota
from chartnexus.infrastructure.catalog import registry
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.time.clock import SystemClock
from chartnexus.shared_kernel.domain.errors import RateLimitError

log = get_logger(__name__)

PROVIDER_NAME = "kite"
IST = ZoneInfo("Asia/Kolkata")

#: How long a user-facing quote may wait for the next one-second window.
_QUOTE_WAIT_SECONDS = 1.1

#: Kite's historical endpoint caps how many days one request may span, per
#: interval. Longer ranges are split into consecutive requests.
_HISTORY_INTERVALS: dict[CandleInterval, tuple[str, int]] = {
    CandleInterval.M1: ("minute", 60),
    CandleInterval.M5: ("5minute", 100),
    CandleInterval.M15: ("15minute", 200),
    CandleInterval.H1: ("60minute", 400),
    CandleInterval.D1: ("day", 2000),
}


class KiteMarketDataProvider:
    """Implements the ``MarketDataProvider`` port."""

    def __init__(
        self,
        *,
        rest: KiteRestClient,
        credentials: BrokerCredentials,
        access_token: str,
        quota: RedisBucketQuota | NullBucketQuota,
        breaker: CircuitBreaker,
        quotes: KiteQuoteCache,
        instruments: KiteInstrumentIndex,
        previous_oi: PreviousOpenInterest,
        retry: RetryPolicy | None = None,
        clock: SystemClock | None = None,
        strikes_each_side: int = 20,
    ) -> None:
        self._rest = rest
        self._credentials = credentials
        self._access_token = access_token
        self._quota = quota
        self._breaker = breaker
        self._quotes = quotes
        self._instruments = instruments
        self._previous_oi = previous_oi
        self._retry = retry or RetryPolicy()
        self._clock = clock or SystemClock()
        self._strikes_each_side = strikes_each_side

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    # -- quotes -----------------------------------------------------------------

    async def get_quote(self, instrument: InstrumentSymbol) -> Quote:
        key = self._spot_key(instrument)
        payload = (await self._quote_map([key])).get(key)
        if payload is None:
            raise BrokerRejectedError(
                f"Zerodha returned no quote for {instrument.value}.", broker=BROKER
            )
        return mappers.to_quote(payload, instrument=instrument, fetched_at=self._clock.now())

    async def get_futures_quote(self, instrument: InstrumentSymbol) -> FuturesQuote:
        contract = await self._future(instrument, series=0)
        payload = (await self._quote_map([contract.quote_key])).get(contract.quote_key)
        if payload is None:
            raise BrokerRejectedError(
                f"Zerodha returned no quote for {contract.tradingsymbol}.", broker=BROKER
            )
        previous = await self._previous_oi.read(self._session(), [contract.instrument_token])
        return mappers.to_futures_quote(
            payload,
            instrument=instrument,
            contract=contract,
            fetched_at=self._clock.now(),
            previous_oi=previous.get(contract.instrument_token),
        )

    async def get_futures_board(
        self, instruments: Sequence[InstrumentSymbol], *, series: int = 0
    ) -> dict[InstrumentSymbol, FuturesQuote]:
        """One series for the whole universe in a single quote request (≤ 500).

        The active contract comes from Zerodha's own listing, so expiry-day
        rolls and holiday-shifted expiries are exact — affordable here because
        the catalog lookup is local, not a request.
        """
        contracts: dict[InstrumentSymbol, KiteInstrument] = {}
        for instrument in instruments:
            try:
                contracts[instrument] = await self._future(instrument, series=series)
            except BrokerRejectedError:
                log.debug("kite_board_no_contract", symbol=instrument.value, series=series)

        quotes = await self._quote_map([contract.quote_key for contract in contracts.values()])
        previous = await self._previous_oi.read(
            self._session(), [contract.instrument_token for contract in contracts.values()]
        )
        now = self._clock.now()
        board: dict[InstrumentSymbol, FuturesQuote] = {}
        for instrument, contract in contracts.items():
            payload = quotes.get(contract.quote_key)
            if payload is None:
                continue
            try:
                board[instrument] = mappers.to_futures_quote(
                    payload,
                    instrument=instrument,
                    contract=contract,
                    fetched_at=now,
                    previous_oi=previous.get(contract.instrument_token),
                )
            except ValueError:
                continue
        return board

    async def get_open_interest(
        self, instrument: InstrumentSymbol, *, series: int = 0
    ) -> OpenInterestReading | None:
        contract = await self._future(instrument, series=series)
        payload = (await self._quote_map([contract.quote_key])).get(contract.quote_key)
        if payload is None:
            return None
        previous = await self._previous_oi.read(self._session(), [contract.instrument_token])
        return mappers.to_open_interest(
            payload,
            instrument=instrument,
            observed_at=self._clock.now(),
            previous_oi=previous.get(contract.instrument_token),
        )

    # -- options ----------------------------------------------------------------

    async def get_expiries(self, instrument: InstrumentSymbol) -> ExpiryList:
        root, exchange = self._underlying(instrument)
        expiries = await self._instruments.option_expiries(root, exchange)
        if not expiries:
            raise BrokerRejectedError(_no_options(instrument), broker=BROKER)
        return ExpiryList(
            instrument=instrument,
            expiries=tuple(expiry.isoformat() for expiry in expiries),
            provenance=Provenance(source=DataSource.LIVE, fetched_at=self._clock.now()),
        )

    async def get_option_chain(
        self, instrument: InstrumentSymbol, expiry: str | None = None
    ) -> OptionChain:
        root, exchange = self._underlying(instrument)
        expiries = await self._instruments.option_expiries(root, exchange)
        if not expiries:
            raise BrokerRejectedError(_no_options(instrument), broker=BROKER)
        chosen = _pick_expiry(expiries, expiry)
        contracts = await self._instruments.options(root, exchange, chosen)

        spot_ref = self._spot_key(instrument)
        # ATM needs the spot first. Usually a cache hit: the page asked for the
        # spot a moment ago, which put it in the hot set.
        spot = (await self._quote_map([spot_ref])).get(spot_ref)
        if spot is None:
            raise BrokerRejectedError(
                f"Zerodha returned no quote for {instrument.value}.", broker=BROKER
            )
        window = _strike_window(contracts, spot.get("last_price"), self._strikes_each_side)

        extras = [spot_ref, _VIX_KEY]
        future = await self._future_or_none(instrument)
        if future is not None:
            extras.append(future.quote_key)
        keys = [*extras, *(contract.quote_key for contract in window)][:QUOTE_BATCH_LIMIT]
        quotes = await self._quote_map(keys)
        previous = await self._previous_oi.read(
            self._session(), [contract.instrument_token for contract in window]
        )

        return mappers.to_option_chain(
            instrument=instrument,
            expiry=chosen,
            expiries=expiries,
            spot=quotes.get(spot_ref) or spot,
            contracts=window,
            quotes=quotes,
            previous_oi=previous,
            fetched_at=self._clock.now(),
            future=quotes.get(future.quote_key) if future is not None else None,
            vix=quotes.get(_VIX_KEY),
        )

    # -- history ----------------------------------------------------------------

    async def get_history(
        self, instrument: InstrumentSymbol, interval: CandleInterval, days: int
    ) -> CandleSeries:
        name, max_days = _HISTORY_INTERVALS[interval]
        listing = self._listing(instrument)
        spot = await self._instruments.spot(instrument.value, listing)
        if spot is None:
            raise BrokerRejectedError(
                f"{instrument.value} is not in the Kite instrument catalog yet.", broker=BROKER
            )

        now = self._clock.now()
        start = now - timedelta(days=max(1, days))
        rows: list[list[Any]] = []
        cursor = start
        while cursor < now:
            chunk_end = min(cursor + timedelta(days=max_days), now)
            rows.extend(
                await self._historical(spot.instrument_token, name, cursor, chunk_end, instrument)
            )
            cursor = chunk_end
        return mappers.to_candle_series(
            rows, instrument=instrument, interval=interval, fetched_at=now
        )

    # -- pre-open capture -------------------------------------------------------

    async def capture_previous_open_interest(self, instruments: Sequence[InstrumentSymbol]) -> int:
        """Record the prior session's closing OI, before the open.

        Before 09:15 Kite's ``oi`` is yesterday's close. This quotes every
        listed future (three series) and each index's option window for its two
        nearest expiries, and stores the readings for today's session. Run by
        the catalog loop right after the morning instrument sync.
        """
        tokens: dict[str, int] = {}
        for instrument in instruments:
            for series in range(3):
                contract = await self._future_or_none(instrument, series=series)
                if contract is not None:
                    tokens[contract.quote_key] = contract.instrument_token
            if instrument.value not in INDEX_SPOTS:
                continue
            spot_ref = self._spot_key(instrument)
            spot = (await self._fetch_direct([spot_ref])).get(spot_ref)
            root, exchange = self._underlying(instrument)
            for expiry in (await self._instruments.option_expiries(root, exchange))[:2]:
                contracts = await self._instruments.options(root, exchange, expiry)
                for contract in _strike_window(
                    contracts, (spot or {}).get("last_price"), self._strikes_each_side
                ):
                    tokens[contract.quote_key] = contract.instrument_token

        readings: dict[int, int] = {}
        keys = list(tokens)
        for start in range(0, len(keys), QUOTE_BATCH_LIMIT):
            batch = keys[start : start + QUOTE_BATCH_LIMIT]
            for key, payload in (await self._fetch_direct(batch)).items():
                oi = payload.get("oi")
                if key in tokens and isinstance(oi, int | float):
                    readings[tokens[key]] = int(oi)
        await self._previous_oi.write(self._session(), readings)
        return len(readings)

    # -- internals --------------------------------------------------------------

    async def _quote_map(self, keys: Sequence[str]) -> dict[str, dict[str, Any]]:
        return await self._quotes.quotes(keys, self._fetch)

    async def _fetch(self, batch: list[str]) -> dict[str, Any]:
        """One guarded quote request. Rate-limit refusal degrades, it does not fail."""
        try:
            await self._quota.acquire("quote", max_wait=_QUOTE_WAIT_SECONDS)
        except RateLimitError as exc:
            # The ladder only degrades on UpstreamError; outside the breaker,
            # so a busy minute never opens the circuit.
            raise BrokerUnavailableError(BROKER) from exc
        quotes: dict[str, Any] = await self._guarded(
            lambda: self._rest.fetch_quotes(
                api_key=self._credentials.app_id,
                access_token=self._access_token,
                instruments=batch,
            ),
            description=f"quote:{len(batch)}",
        )
        return quotes

    async def _fetch_direct(self, batch: list[str]) -> dict[str, Any]:
        """A quote request that bypasses the shared cache (pre-open capture)."""
        return await self._fetch(batch)

    async def _historical(
        self,
        token: int,
        interval: str,
        start: datetime,
        end: datetime,
        instrument: InstrumentSymbol,
    ) -> list[list[Any]]:
        try:
            await self._quota.acquire("historical", max_wait=1.0)
        except RateLimitError as exc:
            raise BrokerUnavailableError(BROKER) from exc
        candles: list[list[Any]] = await self._guarded(
            lambda: self._rest.fetch_historical(
                api_key=self._credentials.app_id,
                access_token=self._access_token,
                instrument_token=token,
                interval=interval,
                start=start.astimezone(IST),
                end=end.astimezone(IST),
            ),
            description=f"history:{instrument.value}:{interval}",
        )
        return candles

    async def _guarded(self, operation, *, description: str):  # type: ignore[no-untyped-def]
        """Breaker outside, retry inside — as in the FYERS provider."""
        return await self._breaker.call(
            lambda: with_retry(operation, policy=self._retry, description=description)
        )

    async def _future(self, instrument: InstrumentSymbol, *, series: int) -> KiteInstrument:
        root, exchange = self._underlying(instrument)
        futures = await self._instruments.futures(root, exchange)
        if series >= len(futures):
            raise BrokerRejectedError(
                f"No listed future (series {series}) for {instrument.value}.", broker=BROKER
            )
        return futures[series]

    async def _future_or_none(
        self, instrument: InstrumentSymbol, *, series: int = 0
    ) -> KiteInstrument | None:
        try:
            return await self._future(instrument, series=series)
        except BrokerRejectedError:
            return None

    def _spot_key(self, instrument: InstrumentSymbol) -> str:
        exchange, symbol = spot_key(instrument.value, self._listing(instrument))
        return f"{exchange}:{symbol}"

    def _listing(self, instrument: InstrumentSymbol) -> str:
        found = registry.current().find(instrument.value)
        return found.exchange if found is not None else "NSE"

    def _underlying(self, instrument: InstrumentSymbol) -> tuple[str, str]:
        found = registry.current().find(instrument.value)
        if found is None:
            return instrument.value, "NSE"
        return (found.futures_root or found.symbol), found.exchange

    def _session(self) -> date:
        return self._clock.now().astimezone(IST).date()


_VIX_KEY = "NSE:INDIA VIX"


def _pick_expiry(expiries: Sequence[date], requested: str | None) -> date:
    """The requested expiry if listed, else the nearest.

    A requested date that is not listed (rolled off, mistyped) falls back to
    the nearest, and the chain is labelled with the expiry it really is.
    """
    if requested:
        try:
            wanted = date.fromisoformat(requested[:10])
        except ValueError:
            wanted = None
        if wanted is not None and wanted in expiries:
            return wanted
    return expiries[0]


def _strike_window(
    contracts: Sequence[KiteInstrument], spot: Any, each_side: int
) -> list[KiteInstrument]:
    """Contracts for the ``each_side`` strikes either side of at-the-money."""
    strikes = sorted({contract.strike for contract in contracts if contract.strike is not None})
    if not strikes:
        return []
    try:
        price = float(spot)
    except (TypeError, ValueError):
        price = float(strikes[len(strikes) // 2])
    atm = min(range(len(strikes)), key=lambda index: abs(float(strikes[index]) - price))
    chosen = set(strikes[max(0, atm - each_side) : atm + each_side + 1])
    return [contract for contract in contracts if contract.strike in chosen]


def _no_options(instrument: InstrumentSymbol) -> str:
    return (
        f"No option contracts for {instrument.value} in the Kite instrument catalog. "
        "It syncs after you connect and every morning at 08:30 IST."
    )
