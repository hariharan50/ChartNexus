"""Where the watcher gets its Fyers credentials.

Reads the broker the user connected in Settings → Broker, rather than a second
copy in environment variables. That was the earlier design and it was wrong in
practice: it meant pasting the same app id and token into two places, and a
token refreshed through the UI left the watcher holding a dead one in `.env`
with nothing to say so.

The same pattern the open-interest sweep uses — ``find_any_active`` — and for
the same reason its comment gives: an index's price is a fact about the
market, not about a tenant, so any one working connection can read it.

Resolved **per session**, never cached for the life of the process. A Fyers
access token expires daily; a watcher that resolved once at startup would be
holding a dead token by the next morning.

Environment variables remain as an override. They are the escape hatch for
running the watcher against a different account from the one the UI is
connected to, and for a deployment with no UI at all — but they are no longer
the normal path, and an unset pair is not an error.
"""

from __future__ import annotations

from typing import Any

from chartnexus.contexts.broker_connections.domain.value_objects import BrokerName
from chartnexus.contexts.trade_buddy.application.ports import BrokerCredentials
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.persistence.postgresql.repositories.integration.broker_connection_repository import (
    SqlAlchemyBrokerConnectionRepository,
)

log = get_logger(__name__)


class ConfiguredCredentials:
    """The environment-variable pair, when both are set. The override path."""

    def __init__(self, app_id: str, access_token: str) -> None:
        self._app_id = app_id
        self._access_token = access_token

    async def fetch(self) -> BrokerCredentials | None:
        if not self._app_id or not self._access_token:
            return None
        return BrokerCredentials(app_id=self._app_id, access_token=self._access_token)


class ConnectedBrokerCredentials:
    """The broker the user connected through the app.

    Falls back to ``override`` when nothing is connected, so a deployment can
    still run on environment variables alone.
    """

    def __init__(self, container: Any, override: ConfiguredCredentials | None = None) -> None:
        self._container = container
        self._override = override

    async def fetch(self) -> BrokerCredentials | None:
        connected = await self._from_database()
        if connected is not None:
            return connected
        if self._override is None:
            return None
        configured = await self._override.fetch()
        if configured is not None:
            log.info("trade_buddy_credentials_from_env")
        return configured

    async def _from_database(self) -> BrokerCredentials | None:
        database = getattr(self._container, "database", None)
        if database is None:
            # The standalone process can be started without a pool; that is a
            # configuration choice, not a failure, and the override still works.
            return None

        try:
            async with database.read_session() as session:
                repository = SqlAlchemyBrokerConnectionRepository(
                    session, self._container.token_cipher
                )
                connection = await repository.find_any_active(BrokerName.FYERS)
        except Exception as exc:
            log.warning("trade_buddy_credentials_read_failed", error=repr(exc))
            return None

        if connection is None:
            log.info("trade_buddy_no_connected_broker")
            return None
        if not connection.is_connected or connection.access_token is None:
            # A connection that exists but is expired or revoked is worth
            # naming: it is the difference between "never set up" and "set up
            # and now stale", and only the second is fixed by reconnecting.
            log.warning("trade_buddy_broker_not_connected", status=str(connection.status))
            return None

        # `credentials` is the connection's own app id/secret pair and is
        # optional on the aggregate — a row can exist with a token but no app
        # id after a partial reconnect, and the socket needs both.
        stored = connection.credentials
        app_id = stored.app_id if stored is not None else ""
        if not app_id:
            log.warning("trade_buddy_broker_missing_app_id")
            return None

        return BrokerCredentials(app_id=app_id, access_token=connection.access_token)
