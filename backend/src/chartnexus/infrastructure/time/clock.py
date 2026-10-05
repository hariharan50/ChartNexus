"""Clock adapters.

Time is injected rather than read directly so that expiry, rotation, and
market-session logic can be tested at a chosen instant instead of by sleeping.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class ReadableClock(Protocol):
    """What an adapter actually needs from a clock: the current instant.

    Most adapters here are annotated ``SystemClock | None`` and are handed a
    ``FixedClock`` by their tests, which type-checks only because nothing
    checks it. This protocol is for the ones that want to say what they mean —
    either class satisfies it, and a test can pin the instant without the
    annotation having to lie.
    """

    def now(self) -> datetime: ...


class SystemClock:
    """Implements the ``Clock`` port. Always UTC-aware."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """A clock frozen at a chosen instant, for tests."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment if moment.tzinfo else moment.replace(tzinfo=UTC)

    def now(self) -> datetime:
        return self._moment

    def advance(self, seconds: float) -> None:
        self._moment += timedelta(seconds=seconds)

    def set(self, moment: datetime) -> None:
        self._moment = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
