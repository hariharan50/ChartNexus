"""Market-data reads, with an explicit degradation ladder.

Every query follows the same sequence:

    fresh cache -> live provider -> last-good cache -> mock

and stamps the result with which rung it landed on. The source architecture is
blunt about why: silently serving synthetic prices to someone sizing a trade is
the failure mode that matters, so degradation is recorded rather than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from marketcompass.contexts.market_data.application.ports import (
    Clock,
    MarketCalendar,
    MarketDataProvider,
    ProviderResolver,
)
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import (
    DataSource,
    ExpiryList,
    FuturesQuote,
    MarketStatus,
    OptionChain,
    Provenance,
    Quote,
)
from marketcompass.shared_kernel.domain.errors import UpstreamError
from marketcompass.shared_kernel.types.identifiers import TenantId

MOCK_PROVIDER_NAME = "mock"


@dataclass(frozen=True, slots=True)
class QuoteQuery:
    tenant_id: TenantId
    instrument: InstrumentSymbol


@dataclass(frozen=True, slots=True)
class OptionChainQuery:
    tenant_id: TenantId
    instrument: InstrumentSymbol
    expiry: str | None = None


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
    ) -> None:
        self._resolver = resolver
        self._fallback = fallback
        self._clock = clock
        self._last_good: dict[str, Quote] = {}

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
                    provenance=_degrade(previous.provenance, self._clock.now()),
                )
            # No real data has ever been seen for this instrument. Serving mock
            # is better than a blank screen, but it is labelled as mock.
            return await self._fallback.get_quote(query.instrument)

        if live:
            self._last_good[key] = quote
        return quote


class GetFuturesQuote(_FallbackMixin):
    """Front-month futures quote, on the same degrade ladder as the spot."""

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
        self._last_good: dict[str, FuturesQuote] = {}

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
            self._last_good[key] = quote
        return quote


class GetOptionChain(_FallbackMixin):
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
        self._last_good: dict[str, OptionChain] = {}

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

        if live:
            self._last_good[key] = chain
        return chain


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
            return await provider.get_expiries(query.instrument)
        except UpstreamError:
            return await self._fallback.get_expiries(query.instrument)


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

        return MarketStatus(
            is_open=self._calendar.is_open(now),
            session_date=now.date().isoformat(),
            time_ist=now.strftime("%H:%M:%S"),
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
