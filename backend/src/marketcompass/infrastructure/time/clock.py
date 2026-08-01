"""Clock adapters.

Time is injected rather than read directly so that expiry, rotation, and
market-session logic can be tested at a chosen instant instead of by sleeping.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


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
