"""Circuit breaker for broker calls.

When the broker is down, continuing to call it wastes the request budget and
makes every page slow by exactly one timeout. After a threshold of consecutive
failures the circuit opens and calls fail instantly, which lets the
degradation ladder reach cached data without the wait.

Per-process state. That is sufficient here: each worker independently discovers
the outage within a few requests, and an open circuit is a performance
optimisation rather than a correctness guarantee.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from chartnexus.contexts.broker_connections.domain.errors import (
    BrokerRejectedError,
    BrokerUnavailableError,
)
from chartnexus.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(slots=True)
class CircuitBreaker:
    failure_threshold: int = 5
    reset_after_seconds: float = 30.0
    name: str = "fyers"

    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)

    @property
    def state(self) -> CircuitState:
        if self._opened_at is None:
            return CircuitState.CLOSED
        if time.monotonic() - self._opened_at >= self.reset_after_seconds:
            # Time to let a single request through and see.
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    async def call[T](self, operation: Callable[[], Awaitable[T]]) -> T:
        if self.state is CircuitState.OPEN:
            raise BrokerUnavailableError

        try:
            result = await operation()
        except BrokerRejectedError:
            # A rejection means the broker is up and answering. It says nothing
            # about availability, so it must not trip the breaker.
            raise
        except BrokerUnavailableError:
            self._record_failure()
            raise

        self._record_success()
        return result

    def _record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold and self._opened_at is None:
            self._opened_at = time.monotonic()
            log.warning(
                "broker_circuit_opened",
                broker=self.name,
                failures=self._failures,
                reset_after_seconds=self.reset_after_seconds,
            )

    def _record_success(self) -> None:
        if self._opened_at is not None:
            log.info("broker_circuit_closed", broker=self.name)
        self._failures = 0
        self._opened_at = None
