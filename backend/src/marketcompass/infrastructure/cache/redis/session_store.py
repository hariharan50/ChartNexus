"""Short-lived server-side storage for in-flight OAuth authorization requests.

Redis rather than a cookie: the PKCE verifier and the nonce must not be visible
to the browser, and the entry has to be destroyable so a ``state`` can only be
redeemed once. The TTL doubles as the deadline for completing a sign-in.
"""

from __future__ import annotations

import json

from marketcompass.contexts.identity.application.ports import PendingAuthorization
from marketcompass.infrastructure.cache.redis.client import RedisClient


class RedisOAuthStateStore:
    """Implements the ``OAuthStateStore`` port."""

    def __init__(self, redis: RedisClient) -> None:
        self._redis = redis

    async def save(
        self,
        state: str,
        *,
        code_verifier: str,
        nonce: str,
        redirect_to: str | None,
        ttl_seconds: int,
    ) -> None:
        payload = json.dumps(
            {"code_verifier": code_verifier, "nonce": nonce, "redirect_to": redirect_to}
        )
        await self._redis.client.set(
            self._key(state),
            payload.encode("utf-8"),
            ex=ttl_seconds,
            # Never overwrite: a colliding state would let one login attempt
            # hijack another's verifier.
            nx=True,
        )

    async def consume(self, state: str) -> PendingAuthorization | None:
        # GETDEL is atomic, so two callbacks racing on the same state cannot
        # both succeed.
        raw = await self._redis.client.getdel(self._key(state))
        if raw is None:
            return None

        try:
            data = json.loads(raw)
            return PendingAuthorization(
                code_verifier=data["code_verifier"],
                nonce=data["nonce"],
                redirect_to=data.get("redirect_to"),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def _key(self, state: str) -> str:
        return self._redis.key("oauth", "state", state)
