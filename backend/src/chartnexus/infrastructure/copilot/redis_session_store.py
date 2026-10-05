"""Server-side conversation memory for the AI Console, scoped to the trading day.

Implements copilot's ``SessionStorePort`` over Redis: the recent text history of
a chat lives under a key that **expires at the end of the IST day**, keyed by
tenant + session id. So a conversation carries across reloads and navigation all
day and resets the next morning — never persisted beyond the day.

Isolation is by **tenant**: the key is ``copilot:session:{tenant}:{session_id}``,
and ``tenant`` comes from the authenticated principal, not the request body. A
client-supplied ``session_id`` can therefore only ever resolve within its own
tenant — it is a conversation handle, not a security boundary.

Only user/assistant text is stored, capped to the newest ``_MAX_TURNS`` for the
model's context. A single answer's internal tool-call blocks are ephemeral: each
new question re-runs the tools against fresh live market data.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta, timezone

from chartnexus.contexts.copilot.application.ports import Session, SessionStorePort, Turn
from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.shared_kernel.types.identifiers import TenantId

# India observes no DST, so a fixed +05:30 offset is correct.
_IST = timezone(timedelta(hours=5, minutes=30))
# A conversation is remembered until the end of the IST trading day, so a chat
# carries across reloads and navigation all day and resets the next morning —
# matching the client, which discards its stored chat when the IST date rolls
# over. A short floor keeps a late-night chat alive briefly past midnight.
_MIN_TTL_SECONDS = 30 * 60
# Cap on remembered turns sent back to the model, so a day-long chat cannot grow
# the context (and cost) without bound. Newest kept; the client still shows the
# full transcript.
_MAX_TURNS = 20


def _seconds_until_ist_end_of_day(now: datetime | None = None) -> int:
    now_ist = (now or datetime.now(UTC)).astimezone(_IST)
    midnight = (now_ist + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(_MIN_TTL_SECONDS, int((midnight - now_ist).total_seconds()))


class RedisSessionStore:
    """Implements ``SessionStorePort`` over the shared Redis pool."""

    def __init__(self, redis: RedisClient, tenant_id: TenantId) -> None:
        self._redis = redis
        self._tenant = str(tenant_id)

    def _key(self, session_id: str) -> str:
        return self._redis.key("copilot:session", self._tenant, session_id)

    async def load(self, session_id: str | None) -> Session:
        # A missing id starts a fresh conversation; a provided one keeps the
        # client's id stable even if its memory has since expired.
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
            # Corrupt entry — start clean rather than fail the request.
            return Session(id=sid, turns=())
        return Session(id=sid, turns=turns)

    async def save(self, session: Session) -> None:
        turns = session.turns[-_MAX_TURNS:]
        payload = json.dumps([{"role": t.role, "text": t.text} for t in turns])
        await self._redis.client.set(
            self._key(session.id), payload, ex=_seconds_until_ist_end_of_day()
        )


# Structural check: RedisSessionStore satisfies the port.
_: type[SessionStorePort] = RedisSessionStore
