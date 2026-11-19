"""In-memory counters for outbound calls, flushed to Redis in batches.

Recording is a dictionary update and nothing else: no await, no I/O, so it adds
nothing measurable to the call being measured. A background task drains the
counters into Redis every :data:`FLUSH_INTERVAL_SECONDS` in one pipeline, and
:meth:`ApiCallRecorder.aclose` drains them a last time at shutdown.

Monitoring must never become the outage. If Redis is unreachable the batch is
dropped with one warning, the counters keep working, and the next flush tries
again; a monitor that queued indefinitely would eventually take the process
down with it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol

from chartnexus.infrastructure.observability.api_monitor.schema import (
    HOUR_TTL_SECONDS,
    MINUTE_TTL_SECONDS,
    RECENT_LIMIT,
    SeriesKey,
    bucket_index,
    encode_field,
    hour_key,
    minute_key,
    recent_key,
)
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)

FLUSH_INTERVAL_SECONDS = 5.0
#: Above this many buffered recent calls, older ones are dropped before flushing.
_RECENT_BUFFER_LIMIT = RECENT_LIMIT
_WARN_EVERY_SECONDS = 60.0


class _RedisLike(Protocol):
    key_prefix: str
    client: Any


@dataclass(frozen=True, slots=True)
class CallOutcome:
    """One finished outbound call. Holds labels and numbers only."""

    series: SeriesKey
    method: str
    elapsed_ms: float
    status: int | None
    error: str | None
    at: float  # epoch seconds


class ApiCallRecorder:
    def __init__(
        self,
        redis: _RedisLike | None,
        *,
        flush_interval: float = FLUSH_INTERVAL_SECONDS,
        enabled: bool = True,
    ) -> None:
        self._redis = redis
        self._interval = flush_interval
        self.enabled = enabled and redis is not None
        # epoch minute -> field -> increment
        self._minutes: dict[int, defaultdict[str, int]] = {}
        self._recent: list[str] = []
        self._task: asyncio.Task[None] | None = None
        self._task_loop: asyncio.AbstractEventLoop | None = None
        self._last_warning = 0.0
        self._closed = False

    # -- capture -----------------------------------------------------------

    def record(self, outcome: CallOutcome) -> None:
        if not self.enabled or self._closed:
            return
        minute = int(outcome.at // 60)
        counters = self._minutes.get(minute)
        if counters is None:
            counters = defaultdict(int)
            self._minutes[minute] = counters
        elapsed = max(0, round(outcome.elapsed_ms))
        counters[encode_field(outcome.series, "n")] += 1
        counters[encode_field(outcome.series, "ms")] += elapsed
        counters[encode_field(outcome.series, f"b{bucket_index(elapsed)}")] += 1
        if outcome.error:
            counters[encode_field(outcome.series, f"e:{outcome.error}")] += 1

        self._recent.append(
            json.dumps(
                {
                    "t": round(outcome.at * 1000),
                    "p": outcome.series.provider,
                    "e": outcome.series.endpoint,
                    "o": outcome.series.origin,
                    "a": outcome.series.app,
                    "m": outcome.method,
                    "s": outcome.status,
                    "x": outcome.error,
                    "ms": elapsed,
                },
                separators=(",", ":"),
            )
        )
        if len(self._recent) > _RECENT_BUFFER_LIMIT:
            del self._recent[: len(self._recent) - _RECENT_BUFFER_LIMIT]
        self._ensure_flusher()

    # -- flushing ----------------------------------------------------------

    def _ensure_flusher(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._task is not None and not self._task.done() and self._task_loop is loop:
            return
        self._task_loop = loop
        self._task = loop.create_task(self._run(), name="api-monitor-flush")

    async def _run(self) -> None:
        while not self._closed:
            await asyncio.sleep(self._interval)
            await self.flush()

    async def flush(self) -> None:
        """Write everything buffered so far. Never raises."""
        if self._redis is None or (not self._minutes and not self._recent):
            return
        minutes, self._minutes = self._minutes, {}
        recent, self._recent = self._recent, []
        prefix = self._redis.key_prefix
        try:
            pipeline = self._redis.client.pipeline(transaction=False)
            hours: dict[int, defaultdict[str, int]] = {}
            for minute, counters in minutes.items():
                key = minute_key(prefix, minute)
                for name, amount in counters.items():
                    pipeline.hincrby(key, name, amount)
                pipeline.expire(key, MINUTE_TTL_SECONDS)
                hour = hours.setdefault(minute // 60, defaultdict(int))
                for name, amount in counters.items():
                    hour[name] += amount
            for hour_number, counters in hours.items():
                key = hour_key(prefix, hour_number)
                for name, amount in counters.items():
                    pipeline.hincrby(key, name, amount)
                pipeline.expire(key, HOUR_TTL_SECONDS)
            if recent:
                key = recent_key(prefix)
                # Newest first, so LPUSH in recording order.
                pipeline.lpush(key, *recent)
                pipeline.ltrim(key, 0, RECENT_LIMIT - 1)
            await pipeline.execute()
        except Exception as exc:  # monitoring must never take the app down
            now = time.monotonic()
            if now - self._last_warning >= _WARN_EVERY_SECONDS:
                self._last_warning = now
                log.warning("api_monitor_flush_failed", error=type(exc).__name__)

    async def aclose(self) -> None:
        self._closed = True
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, RuntimeError):
                await task
        await self.flush()
