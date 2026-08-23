"""The stored pre-market briefing — one per tenant per trading day.

The autonomous worker produces a briefing each morning and persists it; the API
reads back "today's" briefing for the MME100 page. The record is deliberately a
plain markdown document (plus the instruments it covered and the data source), so
the same content can later be delivered over another channel (WhatsApp/Telegram)
without reshaping it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class Briefing:
    """A day's pre-market analysis for one tenant."""

    trading_day: date
    #: The instruments the briefing covered, in order (NIFTY, BANKNIFTY, …).
    instruments: tuple[str, ...]
    #: The full analysis as markdown — the same text the chat agent streams.
    markdown: str
    #: "live" or "mock", derived from whether the reads named simulated data.
    source: str
    #: Set once persisted; ``None`` on a freshly generated, not-yet-stored briefing.
    created_at: datetime | None = None
