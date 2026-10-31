"""Clocks for Trade Buddy — wall time and monotonic time, separately.

``SystemClock`` in ``infrastructure/time`` provides ``now()`` and nothing else,
which is all every other adapter needs. The break hold needs a second source:
measuring a twenty-second confirmation against wall time means an NTP
correction, a VM suspend or a DST-adjacent config change can shorten or
lengthen it, and the failure shows up as a break confirmed by a wick.

``FakeClock`` drives both from one counter, which is what lets the whole state
machine be tested in microseconds with no sleeping.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta


class SystemTradeBuddyClock:
    """Implements the Trade Buddy ``Clock`` port against the real clocks."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()


class FakeClock:
    """A clock with both hands under the test's control.

    ``advance`` moves wall time and monotonic time together by the same amount,
    which is the honest default. Tests that need them to disagree — the NTP-step
    case — can call ``skew`` to move wall time alone.
    """

    def __init__(self, moment: datetime, monotonic: float = 0.0) -> None:
        self._moment = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
        self._monotonic = monotonic

    def now(self) -> datetime:
        return self._moment

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        self._moment += timedelta(seconds=seconds)
        self._monotonic += seconds

    def skew(self, seconds: float) -> None:
        """Move wall time only, leaving the monotonic count alone."""
        self._moment += timedelta(seconds=seconds)

    def set(self, moment: datetime) -> None:
        self._moment = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
