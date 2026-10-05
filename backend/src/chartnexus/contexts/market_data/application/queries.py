"""Market-data reads, with an explicit degradation ladder.

Every query follows the same sequence:

    fresh cache -> live provider -> last-good cache -> mock

and stamps the result with which rung it landed on. The source architecture is
blunt about why: silently serving synthetic prices to someone sizing a trade is
the failure mode that matters, so degradation is recorded rather than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from typing import Final

from chartnexus.contexts.market_data.application.ports import (
    Clock,
    HistoryCachePort,
    IvHistoryRecorder,
    MarketCalendar,
    MarketDataProvider,
    ProviderResolver,
    SessionGapStore,
)
from chartnexus.contexts.market_data.domain.gap import SessionGap, measure, supersedes
from chartnexus.contexts.market_data.domain.implied_volatility import (
    atm_implied_volatility,
    backfill_implied_volatility,
)
from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.contexts.market_data.domain.market_data import (
    CandleInterval,
    CandleSeries,
    DataSource,
    ExpiryList,
    FuturesQuote,
    MarketStatus,
    OptionChain,
    Provenance,
    Quote,
)
from chartnexus.shared_kernel.domain.errors import UpstreamError
from chartnexus.shared_kernel.types.identifiers import TenantId

MOCK_PROVIDER_NAME = "mock"

# India observes no DST; a fixed +05:30 offset matches how ingest capture and
# the OI service both reason about the trading session.
_IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True, slots=True)
class QuoteQuery:
    tenant_id: TenantId
    instrument: InstrumentSymbol


@dataclass(frozen=True, slots=True)
class OptionChainQuery:
    tenant_id: TenantId
    instrument: InstrumentSymbol
    expiry: str | None = None


@dataclass(frozen=True, slots=True)
class HistoryQuery:
    tenant_id: TenantId
    instrument: InstrumentSymbol
    interval: CandleInterval
    days: int


#: Entries kept per last-good store. The universe is 219 instruments across a
#: handful of local tenants, so this holds a whole day's working set and still
#: cannot grow without bound in a long-running worker.
_LAST_GOOD_LIMIT: Final = 512


class LastGood[T]:
    """A bounded, process-lived store of the last real payload per key.

    Deliberately *not* an attribute of the use case. ``build_market_services``
    is a FastAPI dependency, so every request assembles a fresh ``GetSpotPrice``
    with a fresh dictionary - which meant the last-good rung of the documented
    ``fresh -> live -> last-good -> mock`` ladder could never fire even once.
    Every transient broker error fell straight through to the mock provider,
    and the dashboard's gap card alternated between a live gap and the mock's
    seeded one every time the circuit breaker opened and reset.

    Injectable so tests get a clean store instead of inheriting whatever the
    last test left behind in the module-level one.
    """

    __slots__ = ("_entries", "_limit")

    def __init__(self, limit: int = _LAST_GOOD_LIMIT) -> None:
        self._entries: dict[str, T] = {}
        self._limit = limit

    def get(self, key: str) -> T | None:
        return self._entries.get(key)

    def put(self, key: str, value: T) -> None:
        # Re-inserting moves the key to the end, so the eviction below drops the
        # instrument nobody has asked about rather than the one being polled.
        self._entries.pop(key, None)
        self._entries[key] = value
        while len(self._entries) > self._limit:
            self._entries.pop(next(iter(self._entries)))


#: Shared by every request in the process, one per payload shape.
_SPOT_LAST_GOOD: LastGood[Quote] = LastGood()
_FUTURES_LAST_GOOD: LastGood[FuturesQuote] = LastGood()
_CHAIN_LAST_GOOD: LastGood[OptionChain] = LastGood()
_HISTORY_LAST_GOOD: LastGood[CandleSeries] = LastGood()


class _FallbackMixin:
    """Shared live-then-degrade behaviour."""

    _resolver: ProviderResolver
    _fallback: MarketDataProvider
    _clock: Clock

    async def _providers(self, tenant_id: TenantId) -> tuple[MarketDataProvider, bool]:
        provider = await self._resolver.resolve(tenant_id)
        return provider, provider.name != MOCK_PROVIDER_NAME


def _degrade(provenance: Provenance, now: datetime) -> Provenance:
    """Re-stamp a cached payload with its true age at the moment of serving."""
    return Provenance(
        source=DataSource.CACHED,
        fetched_at=provenance.fetched_at,
        age_seconds=max(0.0, (now - provenance.fetched_at).total_seconds()),
    )


class GetSpotPrice(_FallbackMixin):
    def __init__(
        self,
        *,
        resolver: ProviderResolver,
        fallback: MarketDataProvider,
        clock: Clock,
        last_good: LastGood[Quote] | None = None,
    ) -> None:
        self._resolver = resolver
        self._fallback = fallback
        self._clock = clock
        self._last_good = last_good or _SPOT_LAST_GOOD

    async def __call__(self, query: QuoteQuery) -> Quote:
        provider, live = await self._providers(query.tenant_id)
        key = f"{query.tenant_id}:{query.instrument.value}"

        try:
            quote = await provider.get_quote(query.instrument)
        except UpstreamError:
            previous = self._last_good.get(key)
            if previous is not None:
                return Quote(
                    instrument=previous.instrument,
                    price=previous.price,
                    change=previous.change,
                    change_percent=previous.change_percent,
                    day_open=previous.day_open,
                    previous_close=previous.previous_close,
                    provenance=_degrade(previous.provenance, self._clock.now()),
                )
            # No real data has ever been seen for this instrument. Serving mock
            # is better than a blank screen, but it is labelled as mock.
            return await self._fallback.get_quote(query.instrument)

        if live:
            self._last_good.put(key, quote)
        return quote


#: How long after the bell the opening print is treated as provisional.
#:
#: Brokers fill ``open_price`` with the previous session's figure until the
#: auction has actually run, and for a few seconds after it the field can still
#: be corrected. Anything latched inside this window stays replaceable; anything
#: latched after it is the session's opening print and is frozen.
OPENING_SETTLE_MINUTES: Final = 5


class GetSessionGap:
    """The session's opening gap for one instrument, latched for the day.

    Takes a quote that has already been fetched rather than fetching its own:
    the dashboard is polling ``/market/spot`` for three indices every fifteen
    seconds against a capped broker quota, and a gap is a read *over* that
    quote, not a second call.

    What it adds over the two-line subtraction it replaces is durability. The
    first believable pair of the session is written to the store and served from
    there afterwards, so a poll that degrades to the mock cannot rewrite an
    opening print that was observed live. See
    :func:`~chartnexus.contexts.market_data.domain.gap.supersedes` for the
    only two cases in which a latched reading is replaced.
    """

    def __init__(
        self,
        *,
        store: SessionGapStore,
        clock: Clock,
        calendar: MarketCalendar,
    ) -> None:
        self._store = store
        self._clock = clock
        self._calendar = calendar

    async def __call__(self, tenant_id: TenantId, quote: Quote) -> SessionGap | None:
        now = self._clock.now()
        session_date, settled = self._anchor(now)

        observed = measure(
            quote.day_open,
            quote.previous_close,
            source=quote.provenance.source,
            observed_at=now,
            settled=settled,
            reference_price=quote.price,
        )

        latched = await self._read(tenant_id, quote, session_date)
        if latched is None:
            if observed is not None:
                await self._write(tenant_id, quote, session_date, observed)
            return observed

        if observed is not None and supersedes(observed, latched):
            await self._write(tenant_id, quote, session_date, observed)
            return observed
        return latched

    def _anchor(self, now: datetime) -> tuple[date, bool]:
        """The session the gap belongs to, and whether its open has settled.

        A weekend rolls back to Friday, whose session is over by definition -
        without it a Saturday reader would be shown an empty card on a date the
        market never traded. On a weekday the flag turns true once the auction
        has had :data:`OPENING_SETTLE_MINUTES` to produce a real print.
        """
        local = now.astimezone(_IST)
        session_date = local.date()

        weekend_days = local.weekday() - 4
        if weekend_days > 0:
            return session_date - timedelta(days=weekend_days), True

        opens_at = datetime.combine(session_date, self._session_open(), tzinfo=_IST)
        return session_date, local >= opens_at + timedelta(minutes=OPENING_SETTLE_MINUTES)

    def _session_open(self) -> time:
        hour, _, minute = self._calendar.opens_at.partition(":")
        return time(hour=int(hour), minute=int(minute or 0))

    async def _read(
        self, tenant_id: TenantId, quote: Quote, session_date: date
    ) -> SessionGap | None:
        """Read the latch, treating a store failure as a miss.

        The latch is what keeps the card steady, not what makes it correct: if
        Redis is unreachable the reading falls back to whatever this poll
        carries, which is exactly the old behaviour and still better than an
        error page.
        """
        try:
            return await self._store.read(
                tenant_id=tenant_id, instrument=quote.instrument, session_date=session_date
            )
        except Exception:
            return None

    async def _write(
        self, tenant_id: TenantId, quote: Quote, session_date: date, gap: SessionGap
    ) -> None:
        try:
            await self._store.write(
                tenant_id=tenant_id,
                instrument=quote.instrument,
                session_date=session_date,
                gap=gap,
            )
        except Exception:
            # Best-effort, for the same reason as the read: a failed latch costs
            # steadiness on the next poll, it must not cost the reader the card.
            return


class GetFuturesQuote(_FallbackMixin):
    """Front-month futures quote, on the same degrade ladder as the spot."""

    def __init__(
        self,
        *,
        resolver: ProviderResolver,
        fallback: MarketDataProvider,
        clock: Clock,
        last_good: LastGood[FuturesQuote] | None = None,
    ) -> None:
        self._resolver = resolver
        self._fallback = fallback
        self._clock = clock
        self._last_good = last_good or _FUTURES_LAST_GOOD

    async def __call__(self, query: QuoteQuery) -> FuturesQuote:
        provider, live = await self._providers(query.tenant_id)
        key = f"{query.tenant_id}:{query.instrument.value}"

        try:
            quote = await provider.get_futures_quote(query.instrument)
        except UpstreamError:
            previous = self._last_good.get(key)
            if previous is not None:
                return FuturesQuote(
                    instrument=previous.instrument,
                    contract=previous.contract,
                    expiry=previous.expiry,
                    price=previous.price,
                    change=previous.change,
                    change_percent=previous.change_percent,
                    volume=previous.volume,
                    day_high=previous.day_high,
                    day_low=previous.day_low,
                    provenance=_degrade(previous.provenance, self._clock.now()),
                )
            return await self._fallback.get_futures_quote(query.instrument)

        if live:
            self._last_good.put(key, quote)
        return quote


class GetOptionChain(_FallbackMixin):
    def __init__(
        self,
        *,
        resolver: ProviderResolver,
        fallback: MarketDataProvider,
        clock: Clock,
        risk_free_rate: float = 0.07,
        iv_history: IvHistoryRecorder | None = None,
        last_good: LastGood[OptionChain] | None = None,
    ) -> None:
        self._resolver = resolver
        self._fallback = fallback
        self._clock = clock
        self._risk_free_rate = risk_free_rate
        self._iv_history = iv_history
        self._last_good = last_good or _CHAIN_LAST_GOOD

    async def __call__(self, query: OptionChainQuery) -> OptionChain:
        provider, live = await self._providers(query.tenant_id)
        key = f"{query.tenant_id}:{query.instrument.value}:{query.expiry or 'nearest'}"

        try:
            chain = await provider.get_option_chain(query.instrument, query.expiry)
        except UpstreamError:
            previous = self._last_good.get(key)
            if previous is not None:
                return _with_provenance(previous, _degrade(previous.provenance, self._clock.now()))
            return await self._fallback.get_option_chain(query.instrument, query.expiry)

        now = self._clock.now()
        # Backfilling is a no-op wherever a provider (mock, or a future broker)
        # already supplied IV — it only fills legs the broker left blank.
        chain = backfill_implied_volatility(
            chain, valuation_time=now, risk_free_rate=self._risk_free_rate
        )
        chain = await self._with_iv_percentile(chain, query.instrument.value, now)

        if live:
            self._last_good.put(key, chain)
        return chain

    async def _with_iv_percentile(
        self, chain: OptionChain, symbol: str, now: datetime
    ) -> OptionChain:
        if self._iv_history is None:
            return chain
        atm_iv = atm_implied_volatility(chain)
        if atm_iv is None:
            return chain
        rank = await self._iv_history.record_and_rank(
            symbol=symbol, session_date=now.astimezone(_IST).date(), atm_iv=atm_iv
        )
        return replace(chain, iv_percentile=rank)


#: How far out an expiry is worth offering, in days.
#:
#: Six weeklies. A broker will happily list monthlies a quarter out, but nobody
#: reading an intraday options tool is trading them - and every extra entry is
#: one more thing to scroll past in a picker that is used constantly. The cap
#: is applied here rather than in the UI so every caller agrees on the list.
MAX_EXPIRY_HORIZON_DAYS: Final = 42


class GetExpiries(_FallbackMixin):
    def __init__(
        self,
        *,
        resolver: ProviderResolver,
        fallback: MarketDataProvider,
        clock: Clock,
    ) -> None:
        self._resolver = resolver
        self._fallback = fallback
        self._clock = clock

    async def __call__(self, query: QuoteQuery) -> ExpiryList:
        provider, _ = await self._providers(query.tenant_id)
        try:
            listed = await provider.get_expiries(query.instrument)
        except UpstreamError:
            listed = await self._fallback.get_expiries(query.instrument)
        return self._within_horizon(listed)

    def _within_horizon(self, listed: ExpiryList) -> ExpiryList:
        """Drop expiries past the horizon, keeping at least the nearest one.

        The floor matters: on a provider whose next expiry is further out than
        the horizon - a stock with monthly-only expiries, say - a naive filter
        would return an empty list and leave the picker with nothing to choose.
        """
        horizon = self._clock.now().date() + timedelta(days=MAX_EXPIRY_HORIZON_DAYS)
        kept = [expiry for expiry in listed.expiries if _on_or_before(expiry, horizon)]
        if not kept and listed.expiries:
            kept = [listed.expiries[0]]
        if len(kept) == len(listed.expiries):
            return listed
        return replace(listed, expiries=tuple(kept))


class GetHistory(_FallbackMixin):
    """Price bars, on the same degrade ladder as the spot.

    Named for the ``get_history`` the source architecture already prescribes —
    ATR, trend strength and realised volatility are all meant to read from this
    one port, so a second candles-shaped port beside it would be a fork.
    """

    def __init__(
        self,
        *,
        resolver: ProviderResolver,
        fallback: MarketDataProvider,
        clock: Clock,
        cache: HistoryCachePort | None = None,
        cache_retention_days: int = 3,
        last_good: LastGood[CandleSeries] | None = None,
    ) -> None:
        self._resolver = resolver
        self._fallback = fallback
        self._clock = clock
        # A bounded, durable candle cache: write-through on a real fetch, read
        # back when the broker is down. Optional — without it the in-process
        # ``_last_good`` is the only fallback, exactly as before.
        self._cache = cache
        self._cache_retention_days = cache_retention_days
        self._last_good = last_good or _HISTORY_LAST_GOOD

    async def __call__(self, query: HistoryQuery) -> CandleSeries:
        provider, live = await self._providers(query.tenant_id)
        # The range cap belongs here rather than at the router: both providers
        # answer to it, and a request past the broker's per-resolution limit is
        # an error from the broker rather than a slow chart.
        days = max(1, min(query.days, query.interval.max_days))
        key = f"{query.tenant_id}:{query.instrument.value}:{query.interval.value}:{days}"

        try:
            series = await provider.get_history(query.instrument, query.interval, days)
        except UpstreamError:
            return await self._degraded(query, days, key)

        if live:
            self._last_good.put(key, series)
            await self._write_through(series)
        return series

    async def _degraded(self, query: HistoryQuery, days: int, key: str) -> CandleSeries:
        """The broker failed: prefer real-but-stale over synthetic.

        In-process last-good first (this worker served it this run), then the
        durable candle cache (survives a restart), then the mock fallback so the
        chart is never simply empty.
        """
        previous = self._last_good.get(key)
        if previous is not None:
            return replace(previous, provenance=_degrade(previous.provenance, self._clock.now()))
        if self._cache is not None:
            cached = await self._cache.recent(
                query.instrument, query.interval, days=days, now=self._clock.now()
            )
            if cached is not None:
                return cached
        return await self._fallback.get_history(query.instrument, query.interval, days)

    async def _write_through(self, series: CandleSeries) -> None:
        """Persist a real series and drop rows past the retention window.

        Never fails the request: the cache is an optimisation and a fallback, so a
        write error must not take the live answer down with it.
        """
        if self._cache is None or not series.provenance.source.is_real:
            return
        try:
            await self._cache.store(
                series, retain_days=self._cache_retention_days, now=self._clock.now()
            )
        except Exception:
            # Best-effort: the request already has its real series; a failed cache
            # write only forgoes the durable fallback, it does not fail the read.
            return


class GetMarketStatus:
    """What is feeding this tenant, and is the exchange open."""

    def __init__(
        self,
        *,
        resolver: ProviderResolver,
        clock: Clock,
        calendar: MarketCalendar,
    ) -> None:
        self._resolver = resolver
        self._clock = clock
        self._calendar = calendar

    async def __call__(self, tenant_id: TenantId) -> MarketStatus:
        provider = await self._resolver.resolve(tenant_id)
        connected = provider.name != MOCK_PROVIDER_NAME
        now = self._clock.now()
        # The clock is UTC-aware, and both of these fields are exchange-local by
        # name: reading them off the raw instant put the badge 5h30m behind, and
        # rolled the session date a day early after 18:30 IST.
        local = now.astimezone(_IST)

        return MarketStatus(
            is_open=self._calendar.is_open(now),
            session_date=local.date().isoformat(),
            time_ist=local.strftime("%H:%M:%S"),
            provider=provider.name,
            connected=connected,
            source=DataSource.LIVE if connected else DataSource.MOCK,
            market_open=self._calendar.opens_at,
            market_close=self._calendar.closes_at,
        )


def _with_provenance(chain: OptionChain, provenance: Provenance) -> OptionChain:
    return OptionChain(
        instrument=chain.instrument,
        expiry=chain.expiry,
        spot_price=chain.spot_price,
        strikes=chain.strikes,
        provenance=provenance,
        expiries=chain.expiries,
        lot_size=chain.lot_size,
        change_percent=chain.change_percent,
        future_price=chain.future_price,
    )


def _on_or_before(expiry: str, horizon: date) -> bool:
    """Whether ``expiry`` falls on or before ``horizon``.

    An unparseable date is kept: the provider knows its own format better than
    this does, and silently dropping a row would be worse than showing one.
    """
    try:
        return date.fromisoformat(expiry) <= horizon
    except ValueError:
        return True
