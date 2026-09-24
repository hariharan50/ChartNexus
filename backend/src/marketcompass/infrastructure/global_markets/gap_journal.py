"""Where each session's gap prediction is recorded, in Redis.

The same shape the FII/DII cash journal uses, and for the same reason: there is
no archive to read this history back from, so the history is whatever this
deployment has observed. That has to be said on any page that later grades
itself, not papered over by back-filling with something invented.

**Nothing reads this yet.** It is written from the first day because a
prediction is only cheap to record *before* the outcome is known - afterwards
it cannot be reconstructed at all, and a scorecard added later would open with
no history to grade.

Keyed by the session it targets, so the many polls between one close and the
next open overwrite a single entry rather than accumulating hundreds.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from marketcompass.contexts.global_markets.application.ports import GapJournal
from marketcompass.contexts.global_markets.domain.handoff import (
    GapPrediction,
    GapSignal,
    PressureBand,
)
from marketcompass.infrastructure.cache.redis.client import RedisClient
from marketcompass.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

_NAMESPACE: Final = "global-gap-journal"
_FIELD: Final = "sessions"

#: A year of sessions. Long enough to fit weights against, short enough that
#: the hash stays small.
_RETAIN: Final = 260
_TTL_SECONDS: Final = 400 * 24 * 60 * 60


class RedisGapJournal(GapJournal):
    """Implements ``GapJournal``. Never raises - see the port."""

    def __init__(self, redis: RedisClient) -> None:
        self._redis = redis

    async def record(self, prediction: GapPrediction) -> None:
        try:
            key = self._redis.key(_NAMESPACE, _FIELD)
            await self._redis.client.hset(  # type: ignore[misc]
                key, prediction.session.isoformat(), json.dumps(_encode(prediction))
            )
            await self._redis.client.expire(key, _TTL_SECONDS)
        except Exception as exc:
            log.warning("global_gap_journal_write_failed", error=repr(exc))

    async def history(self, sessions: int) -> Sequence[GapPrediction]:
        try:
            raw = await self._redis.client.hgetall(self._redis.key(_NAMESPACE, _FIELD))  # type: ignore[misc]
        except Exception as exc:
            log.warning("global_gap_journal_read_failed", error=repr(exc))
            return ()

        decoded: list[GapPrediction] = []
        for value in (raw or {}).values():
            entry = _decode(value)
            if entry is not None:
                decoded.append(entry)

        decoded.sort(key=lambda item: item.session, reverse=True)
        return tuple(decoded[: min(sessions, _RETAIN)])


def _encode(prediction: GapPrediction) -> dict[str, Any]:
    return {
        "session": prediction.session.isoformat(),
        "recorded_at": prediction.recorded_at.isoformat(),
        "pressure_score": str(prediction.pressure_score),
        "pressure_band": prediction.pressure_band.value,
        "gift_gap_percent": (
            None if prediction.gift_gap_percent is None else str(prediction.gift_gap_percent)
        ),
        "gift_signal": None if prediction.gift_signal is None else prediction.gift_signal.value,
        "actual_gap_percent": (
            None if prediction.actual_gap_percent is None else str(prediction.actual_gap_percent)
        ),
    }


def _decode(value: Any) -> GapPrediction | None:
    try:
        body = json.loads(value if isinstance(value, str) else value.decode())
        return GapPrediction(
            session=date.fromisoformat(body["session"]),
            recorded_at=datetime.fromisoformat(body["recorded_at"]),
            pressure_score=Decimal(body["pressure_score"]),
            pressure_band=PressureBand(body["pressure_band"]),
            gift_gap_percent=_optional_decimal(body.get("gift_gap_percent")),
            gift_signal=(
                None if body.get("gift_signal") is None else GapSignal(body["gift_signal"])
            ),
            actual_gap_percent=_optional_decimal(body.get("actual_gap_percent")),
        )
    except (KeyError, ValueError, TypeError, AttributeError, InvalidOperation):
        # A single unreadable entry must not cost the rest of the history.
        return None


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None
