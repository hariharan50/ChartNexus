"""Chooses which market-data provider serves a tenant.

This is the seam between two bounded contexts that are forbidden to import each
other. ``market_data`` declares the ``ProviderResolver`` port; this adapter
satisfies it by reading a ``broker_connections`` repository. Neither context
learns about the other, and the architecture tests stay green.

There is no provider singleton and no cache to invalidate. A resolver is built
per request and asks the database, so connecting or disconnecting takes effect
on the very next call — including in other worker processes, which a
process-local cache could never manage.
"""

from __future__ import annotations

import httpx

from chartnexus.contexts.broker_connections.application.ports import (
    BrokerConnectionRepository,
)
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
from chartnexus.shared_kernel.types.identifiers import TenantId

log = get_logger(__name__)

# Breakers are keyed by app id and shared across requests in a worker, so an
# outage discovered by one request short-circuits the next.
_BREAKERS: dict[str, CircuitBreaker] = {}


def _breaker_for(app_id: str, *, threshold: int, reset_seconds: float) -> CircuitBreaker:
    breaker = _BREAKERS.get(app_id)
    if breaker is None:
        breaker = CircuitBreaker(failure_threshold=threshold, reset_after_seconds=reset_seconds)
        _BREAKERS[app_id] = breaker
    return breaker


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

    async def resolve(self, tenant_id: TenantId) -> MarketDataProvider:
        """The tenant's live provider, or the mock.

        Never raises for a missing connection: a tenant who has not connected
        yet should see the application work with simulated data, clearly
        labelled, rather than an error page.
        """
        connection = await self._connections.find(tenant_id, BrokerName.FYERS)
        if connection is None:
            return self._fallback

        try:
            credentials = connection.require_credentials()
            access_token = connection.require_access_token()
        except (CredentialsMissingError, NotConnectedError, ConnectionExpiredError):
            return self._fallback

        return FyersMarketDataProvider(
            rest=FyersRestClient(self._http, timeout_seconds=self._timeout),
            credentials=credentials,
            access_token=access_token,
            quota=RedisQuotaManager(self._redis, self._quota),
            breaker=_breaker_for(
                credentials.app_id,
                threshold=self._breaker_threshold,
                reset_seconds=self._breaker_reset,
            ),
        )

    async def is_live(self, tenant_id: TenantId) -> bool:
        connection = await self._connections.find(tenant_id, BrokerName.FYERS)
        return connection is not None and connection.is_connected


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
        if app_id and app_id in _BREAKERS:
            del _BREAKERS[app_id]
            log.info("broker_circuit_reset", broker=broker.value, reason="connection_changed")
