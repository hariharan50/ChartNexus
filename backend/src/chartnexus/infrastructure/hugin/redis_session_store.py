"""Server-side conversation memory for HUGIN's chat, scoped to the trading day.

Implements HUGIN's ``SessionStorePort`` over Redis under its own namespace —
``hugin:session:{tenant}:{session_id}`` — so it never mixes with HELLA/STRYX
memories. The key expires at the end of the IST trading day, so a chat carries
across reloads all day and resets next morning. Isolation is by tenant (from the
authenticated principal), so a client-supplied session id resolves only within its
own tenant.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta, timezone

from chartnexus.contexts.hugin.application.ports import SessionStorePort
from chartnexus.contexts.hugin.domain.conversation import Session, Turn
from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.shared_kernel.types.identifiers import TenantId

_IST = timezone(timedelta(hours=5, minutes=30))
_MIN_TTL_SECONDS = 30 * 60
_MAX_TURNS = 20


def _seconds_until_ist_end_of_day(now: datetime | None = None) -> int:
    now_ist = (now or datetime.now(UTC)).astimezone(_IST)
    midnight = (now_ist + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(_MIN_TTL_SECONDS, int((midnight - now_ist).total_seconds()))


class HuginRedisSessionStore:
    def __init__(self, redis: RedisClient, tenant_id: TenantId) -> None:
        self._redis = redis
        self._tenant = str(tenant_id)

    def _key(self, session_id: str) -> str:
        return self._redis.key("hugin:session", self._tenant, session_id)

    async def load(self, session_id: str | None) -> Session:
        sid = session_id or uuid.uuid4().hex
        if session_id is None:
            return Session(id=sid, turns=())

        raw = await self._redis.client.get(self._key(sid))
        if raw is None:
            return Session(id=sid, turns=())
        try:
            data = json.loads(raw)
            turns = tuple(
                Turn(role=item["role"], text=item["text"])
                for item in data
                if item.get("role") in ("user", "assistant")
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return Session(id=sid, turns=())
        return Session(id=sid, turns=turns)

    async def save(self, session: Session) -> None:
        turns = session.turns[-_MAX_TURNS:]
        payload = json.dumps([{"role": t.role, "text": t.text} for t in turns])
        await self._redis.client.set(
            self._key(session.id), payload, ex=_seconds_until_ist_end_of_day()
        )


# Structural check: HuginRedisSessionStore satisfies the port.
_: type[SessionStorePort] = HuginRedisSessionStore
