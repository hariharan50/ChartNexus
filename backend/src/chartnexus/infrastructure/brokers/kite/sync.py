"""When the Kite catalog is refreshed, and the pre-open OI capture.

Two triggers:

* **Right after a tenant connects Kite** — so the first chain they open works
  without waiting for tomorrow morning.
* **Every morning at ``CN_KITE_CATALOG_SYNC_TIME_IST``** (08:35 by default;
  Zerodha regenerates the dump around 08:30) using whichever Kite connection
  ``find_market_feed`` prefers. Followed, while the market is still closed, by
  the previous-session OI capture that Kite needs for OI change.

Both are best-effort and never raise: a failed sync leaves yesterday's catalog
in place, which still answers every contract except ones listed today.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from chartnexus.contexts.broker_connections.domain.connection import BrokerConnection
from chartnexus.contexts.broker_connections.domain.value_objects import BrokerName
from chartnexus.contexts.instrument_catalog.domain.instrument import InstrumentKind
from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.infrastructure.brokers.kite.catalog import sync_instruments
from chartnexus.infrastructure.brokers.kite.rest_client import KiteEndpoints, KiteRestClient
from chartnexus.infrastructure.catalog import registry
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.persistence.postgresql.repositories.integration.broker_connection_repository import (
    SqlAlchemyBrokerConnectionRepository,
)

log = get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")
#: Before this, Kite's ``oi`` is still the previous session's close.
MARKET_OPEN = time(9, 15)


async def sync_for_connection(container: Any, connection: BrokerConnection) -> int | None:
    """Refresh the Kite catalog with one connection's session. Never raises."""
    if connection.broker is not BrokerName.KITE or connection.credentials is None:
        return None
    token = connection.access_token
    if not token:
        return None
    settings = container.settings.kite
    rest = KiteRestClient(
        container.http,
        endpoints=KiteEndpoints(api_base=settings.api_base, login_url=settings.login_url),
        timeout_seconds=settings.request_timeout_seconds,
    )
    try:
        return await sync_instruments(
            database=container.database,
            rest=rest,
            api_key=connection.credentials.app_id,
            access_token=token,
            equities=_equities(),
        )
    except Exception as exc:  # a bad day must not break the caller
        log.warning("kite_instruments_sync_failed", error=type(exc).__name__, detail=str(exc)[:200])
        return None


async def sync_after_connect(container: Any, tenant_id: Any) -> None:
    """Background task run after a successful Kite login."""
    async with container.database.read_session() as session:
        repository = SqlAlchemyBrokerConnectionRepository(session, container.token_cipher)
        connection = await repository.find(tenant_id, BrokerName.KITE)
    if connection is not None and connection.is_connected:
        await sync_for_connection(container, connection)


async def morning_sync(container: Any) -> None:
    """The daily refresh plus, before the open, the previous-OI capture."""
    async with container.database.read_session() as session:
        repository = SqlAlchemyBrokerConnectionRepository(session, container.token_cipher)
        connection = await repository.find_market_feed()
    if connection is None or connection.broker is not BrokerName.KITE:
        log.info("kite_morning_sync_skipped", reason="no_active_kite_connection")
        return

    if await sync_for_connection(container, connection) is None:
        return
    if datetime.now(IST).time() >= MARKET_OPEN:
        log.info("kite_prev_oi_capture_skipped", reason="market_already_open")
        return
    await capture_previous_oi(container, connection)


async def capture_previous_oi(container: Any, connection: BrokerConnection) -> None:
    # Imported here: provider_resolver imports this package's client lazily,
    # and a module-level import would make the two import each other.
    from chartnexus.infrastructure.brokers.kite.client import (  # noqa: PLC0415
        KiteMarketDataProvider,
    )
    from chartnexus.infrastructure.brokers.provider_resolver import (  # noqa: PLC0415
        build_provider_resolver,
    )

    async with container.database.read_session() as session:
        resolver = build_provider_resolver(
            container, SqlAlchemyBrokerConnectionRepository(session, container.token_cipher)
        )
        provider = resolver.provider_for(connection)
    if not isinstance(provider, KiteMarketDataProvider):
        return
    symbols = [InstrumentSymbol(symbol) for symbol in registry.current().symbols()]
    try:
        stored = await provider.capture_previous_open_interest(symbols)
    except Exception as exc:
        log.warning("kite_prev_oi_capture_failed", error=type(exc).__name__)
        return
    log.info("kite_prev_oi_captured", contracts=stored, at=datetime.now(UTC).isoformat())


def _equities() -> list[str]:
    return [row.symbol for row in registry.current().all() if row.kind is not InstrumentKind.INDEX]
