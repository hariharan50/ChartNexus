"""Chooses which market-data provider serves a tenant.

This is the seam between two bounded contexts that are forbidden to import each
other. ``market_data`` declares the ``ProviderResolver`` port; this adapter
satisfies it by reading a ``broker_connections`` repository. Neither context
learns about the other, and the architecture tests stay green.

There is no provider singleton and no cache to invalidate. A resolver is built
per request and asks the database, so connecting, disconnecting, or switching
broker takes effect on the very next call — including in other worker
processes, which a process-local cache could never manage.

A tenant has one active broker at a time (ADR 0002). Whichever it is — FYERS
or Kite — serves that tenant's data; with none, the labelled mock does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from chartnexus.contexts.broker_connections.application.ports import (
    BrokerConnectionRepository,
)
from chartnexus.contexts.broker_connections.domain.connection import BrokerConnection
from chartnexus.contexts.broker_connections.domain.errors import (
    ConnectionExpiredError,
    CredentialsMissingError,
    NotConnectedError,
)
from chartnexus.contexts.broker_connections.domain.value_objects import BrokerName
from chartnexus.contexts.market_data.application.ports import MarketDataProvider
from chartnexus.infrastructure.brokers.fyers.circuit_breaker import CircuitBreaker
from chartnexus.infrastructure.brokers.fyers.client import FyersMarketDataProvider
from chartnexus.infrastructure.brokers.fyers.quota_manager import (
    QuotaPolicy,
    RedisQuotaManager,
)
from chartnexus.infrastructure.brokers.fyers.rest_client import FyersRestClient
from chartnexus.infrastructure.brokers.mock.provider import MockMarketDataProvider
from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.time.clock import SystemClock
from chartnexus.shared_kernel.types.identifiers import TenantId

log = get_logger(__name__)

# Breakers are keyed by broker and app id and shared across requests in a
# worker, so an outage discovered by one request short-circuits the next.
_BREAKERS: dict[str, CircuitBreaker] = {}


def _breaker_key(broker: BrokerName, app_id: str) -> str:
    return f"{broker.value}:{app_id}"


def _breaker_for(
    broker: BrokerName, app_id: str, *, threshold: int, reset_seconds: float
) -> CircuitBreaker:
    key = _breaker_key(broker, app_id)
    breaker = _BREAKERS.get(key)
    if breaker is None:
        breaker = CircuitBreaker(
            failure_threshold=threshold, reset_after_seconds=reset_seconds, name=broker.value
        )
        _BREAKERS[key] = breaker
    return breaker


@dataclass(frozen=True, slots=True)
class KiteRuntime:
    """What a Kite provider needs beyond the HTTP client.

    ``database`` backs the instrument catalog lookups; ``settings`` is the
    ``KiteSettings`` section. Optional on the resolver so callers that predate
    Kite keep compiling — but every production construction site passes it via
    :func:`build_provider_resolver`.
    """

    database: Any
    settings: Any


class TenantProviderResolver:
    """Implements the ``ProviderResolver`` port."""

    def __init__(
        self,
        *,
        connections: BrokerConnectionRepository,
        http: httpx.AsyncClient,
        redis: RedisClient,
        rest_base_url: str,
        quota: QuotaPolicy,
        request_timeout_seconds: float,
        circuit_breaker_failure_threshold: int,
        circuit_breaker_reset_seconds: float,
        fallback: MarketDataProvider | None = None,
        kite: KiteRuntime | None = None,
    ) -> None:
        self._connections = connections
        self._http = http
        self._redis = redis
        self._rest_base_url = rest_base_url
        self._quota = quota
        self._timeout = request_timeout_seconds
        self._breaker_threshold = circuit_breaker_failure_threshold
        self._breaker_reset = circuit_breaker_reset_seconds
        self._fallback = fallback or MockMarketDataProvider()
        self._kite = kite
        self._clock = SystemClock()

    async def resolve(self, tenant_id: TenantId) -> MarketDataProvider:
        """The tenant's live provider, or the mock.

        Never raises for a missing connection: a tenant who has not connected
        yet should see the application work with simulated data, clearly
        labelled, rather than an error page.
        """
        connection = await self._connections.find_active(tenant_id)
        if connection is None:
            return self._fallback
        return self.provider_for(connection) or self._fallback

    def provider_for(self, connection: BrokerConnection) -> MarketDataProvider | None:
        """A live provider for one stored connection, or ``None`` if it cannot serve.

        Public so background jobs that pick a connection themselves
        (``find_market_feed``) build the provider exactly as requests do.
        """
        try:
            credentials = connection.require_credentials()
            # `now` lets a Kite token past its 06:00 IST logout read as expired
            # without spending a request to be told so.
            access_token = connection.require_access_token(self._clock.now())
        except (CredentialsMissingError, NotConnectedError, ConnectionExpiredError):
            return None

        if connection.broker is BrokerName.KITE:
            return self._kite_provider(connection, access_token)

        return FyersMarketDataProvider(
            rest=FyersRestClient(self._http, timeout_seconds=self._timeout),
            credentials=credentials,
            access_token=access_token,
            quota=RedisQuotaManager(self._redis, self._quota),
            breaker=_breaker_for(
                BrokerName.FYERS,
                credentials.app_id,
                threshold=self._breaker_threshold,
                reset_seconds=self._breaker_reset,
            ),
        )

    def _kite_provider(
        self, connection: BrokerConnection, access_token: str
    ) -> MarketDataProvider | None:
        if self._kite is None:
            log.warning("kite_provider_unavailable", reason="resolver_built_without_kite_runtime")
            return None
        # Imported here: the Kite package pulls in the persistence layer for its
        # catalog, which callers that never meet a Kite tenant need not load.
        from chartnexus.infrastructure.brokers.kite.catalog import (  # noqa: PLC0415
            KiteInstrumentIndex,
        )
        from chartnexus.infrastructure.brokers.kite.client import (  # noqa: PLC0415
            KiteMarketDataProvider,
        )
        from chartnexus.infrastructure.brokers.kite.prev_oi import (  # noqa: PLC0415
            PreviousOpenInterest,
        )
        from chartnexus.infrastructure.brokers.kite.quote_cache import (  # noqa: PLC0415
            KiteQuoteCache,
        )
        from chartnexus.infrastructure.brokers.kite.rest_client import (  # noqa: PLC0415
            KiteEndpoints,
            KiteRestClient,
        )
        from chartnexus.infrastructure.brokers.quota import (  # noqa: PLC0415
            BucketPolicy,
            RedisBucketQuota,
        )

        credentials = connection.require_credentials()
        settings = self._kite.settings
        return KiteMarketDataProvider(
            rest=KiteRestClient(
                self._http,
                endpoints=KiteEndpoints(api_base=settings.api_base, login_url=settings.login_url),
                timeout_seconds=settings.request_timeout_seconds,
            ),
            credentials=credentials,
            access_token=access_token,
            quota=RedisBucketQuota(
                self._redis,
                broker=BrokerName.KITE.value,
                app_key=credentials.app_id,
                policy=BucketPolicy(
                    per_second={
                        "quote": settings.quote_requests_per_second,
                        "historical": settings.historical_requests_per_second,
                        "other": settings.other_requests_per_second,
                    },
                    per_day=settings.requests_per_day,
                ),
            ),
            breaker=_breaker_for(
                BrokerName.KITE,
                credentials.app_id,
                threshold=self._breaker_threshold,
                reset_seconds=self._breaker_reset,
            ),
            quotes=KiteQuoteCache(
                self._redis,
                api_key=credentials.app_id,
                ttl_seconds=settings.quote_cache_seconds,
                hot_seconds=settings.hot_set_seconds,
            ),
            instruments=KiteInstrumentIndex(self._kite.database),
            previous_oi=PreviousOpenInterest(self._redis),
            strikes_each_side=settings.strikes_each_side,
        )

    async def is_live(self, tenant_id: TenantId) -> bool:
        connection = await self._connections.find_active(tenant_id)
        return (
            connection is not None
            and connection.is_connected
            and not connection.has_lapsed(self._clock.now())
        )


def build_provider_resolver(
    container: Any,
    connections: BrokerConnectionRepository,
    *,
    fallback: MarketDataProvider | None = None,
) -> TenantProviderResolver:
    """The resolver every request handler and background job should use.

    One construction site, so a new broker or setting is wired once rather than
    in each of the places that read market data.
    """
    settings = container.settings
    return TenantProviderResolver(
        connections=connections,
        http=container.http,
        redis=container.redis,
        rest_base_url=settings.broker.rest_base_url,
        quota=QuotaPolicy(
            requests_per_second=settings.broker.quota_requests_per_second,
            requests_per_day=settings.broker.quota_requests_per_day,
        ),
        request_timeout_seconds=settings.broker.request_timeout_seconds,
        circuit_breaker_failure_threshold=settings.broker.circuit_breaker_failure_threshold,
        circuit_breaker_reset_seconds=settings.broker.circuit_breaker_reset_seconds,
        fallback=fallback,
        kite=KiteRuntime(database=getattr(container, "database", None), settings=settings.kite),
    )


class ConnectionCacheReset:
    """Implements the ``ConnectionCacheInvalidator`` port.

    With providers built per request there is no client cache to clear. What
    does persist is the circuit breaker, and a reconnect should not inherit an
    open circuit from the credentials that just got replaced.
    """

    def __init__(self, connections: BrokerConnectionRepository) -> None:
        self._connections = connections

    async def invalidate(self, tenant_id: TenantId, broker: BrokerName) -> None:
        connection = await self._connections.find(tenant_id, broker)
        app_id = connection.credentials.app_id if connection and connection.credentials else None
        if not app_id:
            return
        key = _breaker_key(broker, app_id)
        if key in _BREAKERS:
            del _BREAKERS[key]
            log.info("broker_circuit_reset", broker=broker.value, reason="connection_changed")
