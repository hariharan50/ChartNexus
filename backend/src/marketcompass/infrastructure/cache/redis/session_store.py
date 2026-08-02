"""Short-lived server-side storage for in-flight OAuth authorization requests.

Redis rather than a cookie: PKCE verifiers, nonces, and the tenant a connection
attempt belongs to must not be visible to or forgeable by the browser. The entry
has to be destroyable so a ``state`` can only be redeemed once, and the TTL
doubles as the deadline for completing the flow.

Two stores share the mechanism: sign-in with Google, and connecting a broker.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from marketcompass.contexts.broker_connections.application.ports import PendingConnection
from marketcompass.contexts.broker_connections.domain.value_objects import BrokerName
from marketcompass.contexts.identity.application.ports import PendingAuthorization
from marketcompass.infrastructure.cache.redis.client import RedisClient
from marketcompass.shared_kernel.types.identifiers import TenantId, UserId


class _SingleUseStateStore:
    """One-shot, TTL-bounded state storage.

    Writes are ``nx=True`` so a colliding state cannot hijack another attempt's
    payload, and reads are ``GETDEL`` so two callbacks racing on the same state
    cannot both succeed.
    """

    def __init__(self, redis: RedisClient, namespace: str) -> None:
        self._redis = redis
        self._namespace = namespace

    async def put(self, state: str, payload: dict[str, Any], *, ttl_seconds: int) -> None:
        await self._redis.client.set(
            self._key(state),
            json.dumps(payload).encode("utf-8"),
            ex=ttl_seconds,
            nx=True,
        )

    async def take(self, state: str) -> dict[str, Any] | None:
        raw = await self._redis.client.getdel(self._key(state))
        if raw is None:
            return None
        try:
            data: dict[str, Any] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        return data

    def _key(self, state: str) -> str:
        return self._redis.key("oauth", self._namespace, state)


class RedisOAuthStateStore:
    """Implements the identity ``OAuthStateStore`` port (Google sign-in)."""

    def __init__(self, redis: RedisClient) -> None:
        self._store = _SingleUseStateStore(redis, "state")

    async def save(
        self,
        state: str,
        *,
        code_verifier: str,
        nonce: str,
        redirect_to: str | None,
        ttl_seconds: int,
    ) -> None:
        await self._store.put(
            state,
            {"code_verifier": code_verifier, "nonce": nonce, "redirect_to": redirect_to},
            ttl_seconds=ttl_seconds,
        )

    async def consume(self, state: str) -> PendingAuthorization | None:
        data = await self._store.take(state)
        if data is None:
            return None
        try:
            return PendingAuthorization(
                code_verifier=data["code_verifier"],
                nonce=data["nonce"],
                redirect_to=data.get("redirect_to"),
            )
        except (KeyError, TypeError):
            return None


class RedisConnectStateStore:
    """Implements the broker ``ConnectStateStore`` port.

    The stored tenant is what the callback trusts. Nothing the browser sends
    back decides which tenant a broker token is attached to.
    """

    def __init__(self, redis: RedisClient) -> None:
        self._store = _SingleUseStateStore(redis, "broker-connect")

    async def save(self, state: str, pending: PendingConnection, *, ttl_seconds: int) -> None:
        await self._store.put(
            state,
            {
                "tenant_id": str(pending.tenant_id),
                "user_id": str(pending.user_id),
                "broker": pending.broker.value,
                "redirect_to": pending.redirect_to,
            },
            ttl_seconds=ttl_seconds,
        )

    async def consume(self, state: str) -> PendingConnection | None:
        data = await self._store.take(state)
        if data is None:
            return None
        try:
            return PendingConnection(
                tenant_id=TenantId(uuid.UUID(data["tenant_id"])),
                user_id=UserId(uuid.UUID(data["user_id"])),
                broker=BrokerName(data["broker"]),
                redirect_to=data.get("redirect_to"),
            )
        except (KeyError, TypeError, ValueError):
            # Corrupt or hand-crafted payload. Indistinguishable from an
            # unknown state, which is the correct response either way.
            return None
