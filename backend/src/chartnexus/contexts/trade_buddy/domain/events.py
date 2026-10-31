"""What the watcher can say about a level, and nothing about how it is said.

Six kinds, because six is what the state machine can distinguish. The split that
matters is not severity but *confirmation*: ``APPROACHING`` and ``TOUCHED`` are
observations about where price is right now, while ``BREAK_CONFIRMED``,
``RECLAIMED`` and ``GAPPED_THROUGH`` are assertions that something has happened
and will not un-happen. ``WICK_REJECTED`` is the one that exists purely to be
*visible without being loud* — it is the evidence that the hold window did its
job, and it is the reason a trader can trust the absence of a break alert.

Routing and throttling read ``kind`` and nothing else, which is why the policy
tables elsewhere can be written as plain sets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from chartnexus.contexts.trade_buddy.domain.level import LevelRole


class AlertKind(StrEnum):
    """The six things the engine can emit about one level."""

    APPROACHING = "approaching"
    TOUCHED = "touched"
    BREAK_CONFIRMED = "break_confirmed"
    WICK_REJECTED = "wick_rejected"
    RECLAIMED = "reclaimed"
    GAPPED_THROUGH = "gapped_through"


#: Events that assert a completed, non-reversible fact. These are never dropped
#: by a cooldown or a daily cap — a missed real break is one of the two failure
#: modes this module exists to avoid. Throttling protects against noise, and a
#: confirmed break is by definition not noise.
CONFIRMED_KINDS = frozenset(
    {
        AlertKind.BREAK_CONFIRMED,
        AlertKind.RECLAIMED,
        AlertKind.GAPPED_THROUGH,
    }
)

#: Events that describe where price is at this instant. Throttled, because price
#: loitering near a level can produce these indefinitely.
OBSERVATION_KINDS = frozenset(
    {
        AlertKind.APPROACHING,
        AlertKind.TOUCHED,
        AlertKind.WICK_REJECTED,
    }
)


@dataclass(frozen=True, slots=True)
class AlertEvent:
    """One thing that happened to one level, with the numbers that justify it.

    Carries ``price`` and ``level_price`` rather than a rendered string so the
    notifiers own their own formatting — Telegram gets HTML, CallMeBot gets
    plain text, and neither has to parse the other's wording.
    """

    kind: AlertKind
    symbol: str
    #: The level's label as the user marked it, e.g. ``"R2"``.
    label: str
    #: The marked price of the level.
    level_price: float
    #: The price that triggered this event.
    price: float
    #: The role the level held *before* this event. A confirmed break flips it,
    #: and the alert text says so, so the reader knows what the level is now.
    role_before: LevelRole
    #: The role the level holds *after* this event.
    role_after: LevelRole
    at: datetime

    @property
    def flipped(self) -> bool:
        """True when this event changed the level's role (support ⇄ resistance)."""
        return self.role_before is not self.role_after

    @property
    def distance(self) -> float:
        """Signed points from the level to the triggering price."""
        return self.price - self.level_price
