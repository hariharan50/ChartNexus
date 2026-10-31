"""What may be sent, and over which channel. Throttling lives here, not in the
state machine — the watcher reports what happened, this decides what is heard.

Two independent limiters, for two different reasons:

:class:`LevelBudget` protects the *reader*. Price loitering inside an approach
band can generate observations forever, so each level gets a cooldown and a
daily cap. Confirmed events bypass both, by explicit policy: a cap that can
swallow a real break has made the alerting worse than none, because silence
would at least be honest.

:class:`WhatsAppBudget` protects the *channel*. CallMeBot throttles at roughly
25 messages per four hours and fails opaquely once past it. Counting locally
means the engine can see the budget running out and fall back to Telegram-only
while it still has something to fall back with — degrading loudly beats
discovering at 15:00 that nothing has been delivered since noon.

Both are pure and clock-injected, so a four-hour window is testable without
waiting four hours.
"""

from __future__ import annotations

from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from chartnexus.contexts.trade_buddy.domain.events import (
    CONFIRMED_KINDS,
    AlertEvent,
    AlertKind,
)


def _cooldown_key(label: str, kind: AlertKind) -> str:
    """One cooldown slot per (level, kind).

    A plain string rather than a tuple so :meth:`LevelBudget.snapshot` stays
    directly JSON-serialisable — the store writes it verbatim.
    """
    return f"{label}|{kind.value}"


@dataclass(slots=True)
class LevelBudget:
    """Per-level cooldown and daily cap over *observation* events only."""

    cooldown: timedelta = timedelta(minutes=20)
    daily_cap: int = 3
    #: Last time an observation was allowed through, keyed by level *and kind*.
    #:
    #: Per-kind, not per-level alone, and this is load-bearing. A single
    #: per-level timer meant an APPROACHING at 09:20 silenced the TOUCHED at
    #: 09:21 for the next twenty minutes — but approach → touch → break is an
    #: *escalation*, and each step is information the reader would act on. The
    #: thing worth suppressing is the same observation repeating, which this
    #: still does.
    _last_sent: dict[str, datetime] = field(default_factory=dict)
    #: Observations allowed through today, per level label. Per level, because
    #: the cap is the reader's total tolerance for one price — "3 alerts/level".
    _sent_today: dict[str, int] = field(default_factory=dict)
    _day: date | None = None

    def allow(self, event: AlertEvent) -> bool:
        """Whether ``event`` may be delivered. Records the decision when yes.

        Confirmed events are always allowed and never counted — counting them
        would let a burst of breaks exhaust a budget that then suppresses the
        next break.
        """
        self._roll_day(event.at.date())

        if event.kind in CONFIRMED_KINDS:
            return True

        if self._sent_today.get(event.label, 0) >= self.daily_cap:
            return False

        key = _cooldown_key(event.label, event.kind)
        last = self._last_sent.get(key)
        if last is not None and event.at - last < self.cooldown:
            return False

        self._last_sent[key] = event.at
        self._sent_today[event.label] = self._sent_today.get(event.label, 0) + 1
        return True

    def remaining(self, label: str) -> int:
        """Observations still available for one level today. For the state route."""
        return max(0, self.daily_cap - self._sent_today.get(label, 0))

    # -- persistence --------------------------------------------------------
    #
    # The counters have to outlive the process. Without this a restart at 14:00
    # hands every level a fresh cap and an expired cooldown, and the afternoon
    # replays alerts the morning already sent — the exact "re-fire for ground
    # already covered" this feature was told to avoid.

    def snapshot(self) -> dict[str, object]:
        return {
            "day": self._day.isoformat() if self._day else None,
            "last_sent": {label: moment.isoformat() for label, moment in self._last_sent.items()},
            "sent_today": dict(self._sent_today),
        }

    def restore(self, state: dict[str, object]) -> None:
        """Reload counters saved by :meth:`snapshot`. Tolerant of a partial blob.

        A malformed field is skipped rather than raised on: losing a cooldown is
        a cosmetic failure, while refusing to start the watcher is not.
        """
        day = state.get("day")
        if isinstance(day, str):
            with suppress(ValueError):
                self._day = date.fromisoformat(day)

        last_sent = state.get("last_sent")
        if isinstance(last_sent, dict):
            for label, raw in last_sent.items():
                if isinstance(raw, str):
                    with suppress(ValueError):
                        self._last_sent[str(label)] = datetime.fromisoformat(raw)

        sent_today = state.get("sent_today")
        if isinstance(sent_today, dict):
            for label, count in sent_today.items():
                if isinstance(count, int):
                    self._sent_today[str(label)] = count

    def _roll_day(self, today: date) -> None:
        """Reset the per-day counters when the session date changes.

        Keyed on the event's own date rather than "now" so a replay of
        yesterday's ticks cannot clear today's counts.
        """
        if self._day != today:
            self._day = today
            self._sent_today.clear()
            self._last_sent.clear()


@dataclass(slots=True)
class WhatsAppBudget:
    """A rolling-window send count for the WhatsApp relay.

    Deliberately conservative: ``limit`` should be set below CallMeBot's actual
    ceiling, because exceeding it is not a rejected message but an unreliable
    one, and a notifier you cannot trust is worse than one you know is off.
    """

    limit: int = 20
    window: timedelta = timedelta(hours=4)
    _sends: deque[datetime] = field(default_factory=deque)

    def _evict(self, now: datetime) -> None:
        cutoff = now - self.window
        while self._sends and self._sends[0] <= cutoff:
            self._sends.popleft()

    def available(self, now: datetime) -> bool:
        self._evict(now)
        return len(self._sends) < self.limit

    def record(self, now: datetime) -> None:
        """Count a send. Call only after the send actually succeeded."""
        self._evict(now)
        self._sends.append(now)

    def used(self, now: datetime) -> int:
        self._evict(now)
        return len(self._sends)

    def snapshot(self) -> list[str]:
        """ISO timestamps of the sends still in the window, for persistence."""
        return [moment.isoformat() for moment in self._sends]

    def reload(self, stamps: list[str]) -> None:
        """Replace the window from :meth:`snapshot`, keeping limit and window.

        The instance-level counterpart to :meth:`restore`: the engine holds a
        budget the router already owns, so it refills that one rather than
        swapping in a new object the router would never see.
        """
        self._sends.clear()
        for stamp in sorted(stamps):
            with suppress(ValueError):
                self._sends.append(datetime.fromisoformat(stamp))

    @classmethod
    def restore(
        cls, stamps: list[str], *, limit: int = 20, window: timedelta = timedelta(hours=4)
    ) -> WhatsAppBudget:
        """Rebuild from :meth:`snapshot`.

        A restart must not hand the process a fresh 25-message allowance — the
        provider is counting whether or not we are.
        """
        budget = cls(limit=limit, window=window)
        budget._sends.extend(sorted(datetime.fromisoformat(stamp) for stamp in stamps))
        return budget
