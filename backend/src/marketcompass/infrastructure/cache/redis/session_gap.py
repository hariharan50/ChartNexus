"""The session's latched opening gap, in Redis.

Redis rather than a process dictionary for two reasons. The market services are
assembled per request, so nothing held on the use case survives to the next poll
- that is the defect this store exists to close. And the API runs behind more
than one worker: a latch held in one process would let a reader's gap change
depending on which worker answered, which is the same flapping wearing a
different hat.

One key per tenant, instrument and session date, expiring well after the close
so a quiet weekend never carries Friday's opening print into Monday.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from marketcompass.contexts.market_data.domain.gap import GapSignal, SessionGap
from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.contexts.market_data.domain.market_data import DataSource
from marketcompass.infrastructure.cache.redis.client import RedisClient
from marketcompass.shared_kernel.types.identifiers import TenantId

#: A session plus slack. Long enough that a latch written at 09:15 is still
#: there for a reader at 23:00; short enough that it can never be mistaken for
#: the next session's open.
_TTL_SECONDS = 26 * 60 * 60


class RedisSessionGapStore:
    """Implements ``market_data``'s ``SessionGapStore`` port."""

    def __init__(self, redis: RedisClient) -> None:
        self._redis = redis

    async def read(
        self, *, tenant_id: TenantId, instrument: InstrumentSymbol, session_date: date
    ) -> SessionGap | None:
        raw = await self._redis.client.get(self._key(tenant_id, instrument, session_date))
        if raw is None:
            return None
        try:
            return _decode(json.loads(raw))
        except (ValueError, KeyError, TypeError):
            # A payload written by an older shape of this record. Dropping it is
            # right: the next poll re-latches from a live quote within seconds,
            # whereas raising would take the whole spot response down with it.
            return None

    async def write(
        self,
        *,
        tenant_id: TenantId,
        instrument: InstrumentSymbol,
        session_date: date,
        gap: SessionGap,
    ) -> None:
        await self._redis.client.set(
            self._key(tenant_id, instrument, session_date),
            json.dumps(_encode(gap)),
            ex=_TTL_SECONDS,
        )

    def _key(self, tenant_id: TenantId, instrument: InstrumentSymbol, session_date: date) -> str:
        return self._redis.key(
            "session-gap", str(tenant_id), instrument.value, session_date.isoformat()
        )


def _encode(gap: SessionGap) -> dict[str, Any]:
    # Decimals go over as strings, never floats: the opening print is a price,
    # and a round trip through binary floating point would move it.
    return {
        "opened_at": str(gap.opened_at),
        "reference_close": str(gap.reference_close),
        "points": str(gap.points),
        "percent": str(gap.percent),
        "signal": gap.signal.value,
        "source": gap.source.value,
        "observed_at": gap.observed_at.isoformat(),
        "settled": gap.settled,
    }


def _decode(payload: dict[str, Any]) -> SessionGap:
    return SessionGap(
        opened_at=Decimal(payload["opened_at"]),
        reference_close=Decimal(payload["reference_close"]),
        points=Decimal(payload["points"]),
        percent=Decimal(payload["percent"]),
        signal=GapSignal(payload["signal"]),
        source=DataSource(payload["source"]),
        observed_at=datetime.fromisoformat(payload["observed_at"]),
        settled=bool(payload["settled"]),
    )
