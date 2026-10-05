"""Retry policy for broker calls.

The rule that matters: **never retry an authentication failure.** A rejected
token will be rejected again, and hammering the endpoint is how an application
gets rate-limited or blocked. Only transient conditions — timeouts, 5xx, and
explicit rate-limit responses — are retried, with jitter so a fleet of workers
does not resynchronise into a thundering herd.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from chartnexus.contexts.broker_connections.domain.errors import (
    BrokerRejectedError,
    BrokerUnavailableError,
)
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    initial_delay_seconds: float = 0.25
    max_delay_seconds: float = 4.0
    jitter: float = 0.3

    def delay_for(self, attempt: int) -> float:
        """Exponential backoff with proportional jitter."""
        base = min(self.initial_delay_seconds * (2**attempt), self.max_delay_seconds)
        spread = base * self.jitter
        jittered = base + random.uniform(-spread, spread)  # noqa: S311 — jitter, not crypto
        return max(0.0, float(jittered))


async def with_retry[T](
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    description: str = "broker call",
) -> T:
    resolved = policy or RetryPolicy()
    last_error: BrokerUnavailableError | None = None

    for attempt in range(resolved.attempts):
        try:
            return await operation()
        except BrokerRejectedError:
            # Deliberate: a rejection is a decision, not a hiccup. Retrying it
            # cannot change the answer.
            raise
        except BrokerUnavailableError as exc:
            last_error = exc
            if attempt == resolved.attempts - 1:
                break
            delay = resolved.delay_for(attempt)
            log.warning(
                "broker_retry",
                operation=description,
                attempt=attempt + 1,
                of=resolved.attempts,
                delay_seconds=round(delay, 3),
            )
            await asyncio.sleep(delay)

    raise last_error if last_error else BrokerUnavailableError
