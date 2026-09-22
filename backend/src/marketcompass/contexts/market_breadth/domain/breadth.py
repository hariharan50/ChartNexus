"""Advance/decline arithmetic.

How many index members are up, down, and genuinely flat — overall and per
sector. The whole module is counting, and its only real decision is what
counts as flat: see ``DEFAULT_DEADBAND_PERCENT``. A stock that ticked one
paisa is not "advancing", and a breadth reading that says it is turns a quiet
session into a false signal.

The advance/decline *ratio* is advances over declines, the way a desk quotes
it. It is deliberately ``None`` when nothing declined rather than infinity or
a sentinel: "everything is up" is a fact about the counts, and the counts are
right there beside it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from marketcompass.contexts.market_breadth.domain.constituents import (
    DEFAULT_DEADBAND_PERCENT,
    Constituent,
)


@dataclass(frozen=True, slots=True)
class BreadthCount:
    """Advancing, declining and unchanged, plus the members that had no price."""

    advancing: int = 0
    declining: int = 0
    unchanged: int = 0
    #: Members the feed could not price at all. Counted separately from
    #: ``unchanged``: "did not move" and "we do not know" are different facts.
    unpriced: int = 0

    @property
    def counted(self) -> int:
        """Members that produced a usable reading."""
        return self.advancing + self.declining + self.unchanged

    @property
    def ratio(self) -> Decimal | None:
        """Advances per decline, or ``None`` when nothing declined."""
        if self.declining == 0:
            return None
        return (Decimal(self.advancing) / Decimal(self.declining)).quantize(Decimal("0.01"))

    @property
    def advancing_percent(self) -> Decimal | None:
        """Share of *counted* members that advanced, 0-100."""
        if self.counted == 0:
            return None
        return Decimal(self.advancing) / Decimal(self.counted) * Decimal(100)

    @property
    def net(self) -> int:
        """Advances minus declines — the number the A/D line accumulates."""
        return self.advancing - self.declining


@dataclass(frozen=True, slots=True)
class SectorBreadth:
    """One sector's slice of the index, counted and weighted."""

    sector: str
    count: BreadthCount
    #: Combined index weight of this sector's priced members.
    weight_percent: Decimal
    #: Weight-averaged move of those members, which is what the sector actually
    #: contributed in direction — a simple mean would let a 0.3%-weight name
    #: shout as loudly as a 13% one.
    weighted_change_percent: Decimal | None
    members: tuple[Constituent, ...] = ()


def count_breadth(
    members: Sequence[Constituent],
    *,
    deadband_percent: Decimal = DEFAULT_DEADBAND_PERCENT,
) -> BreadthCount:
    """Classify each member as advancing, declining, unchanged or unpriced."""
    advancing = declining = unchanged = unpriced = 0
    for member in members:
        change = member.change_percent
        if change is None:
            unpriced += 1
        elif change > deadband_percent:
            advancing += 1
        elif change < -deadband_percent:
            declining += 1
        else:
            unchanged += 1
    return BreadthCount(
        advancing=advancing, declining=declining, unchanged=unchanged, unpriced=unpriced
    )


def breadth_by_sector(
    members: Sequence[Constituent],
    *,
    deadband_percent: Decimal = DEFAULT_DEADBAND_PERCENT,
) -> list[SectorBreadth]:
    """Per-sector breadth, heaviest sector first.

    Members with no sector are grouped under ``UNCLASSIFIED`` rather than
    dropped: they are still in the index, and silently excluding them would
    make the sector weights sum to less than the coverage figure claims.
    """
    buckets: dict[str, list[Constituent]] = {}
    for member in members:
        buckets.setdefault(member.sector or UNCLASSIFIED, []).append(member)

    out = [
        SectorBreadth(
            sector=sector,
            count=count_breadth(group, deadband_percent=deadband_percent),
            weight_percent=_weight_of(group),
            weighted_change_percent=weighted_change(group),
            members=tuple(sorted(group, key=_by_weight_desc)),
        )
        for sector, group in buckets.items()
    ]
    out.sort(key=lambda entry: (-entry.weight_percent, entry.sector))
    return out


#: Where a member with no sector classification lands. Named rather than
#: inlined so the API layer and the tests agree on the spelling.
UNCLASSIFIED = "UNCLASSIFIED"


def weighted_change(members: Sequence[Constituent]) -> Decimal | None:
    """Weight-averaged percentage move across the priced members.

    ``None`` when nothing in the group could be priced, or when every priced
    member carries zero weight — both mean the average has no denominator, and
    returning 0.00% would claim the group was flat.
    """
    total_weight = Decimal(0)
    weighted = Decimal(0)
    for member in members:
        change = member.change_percent
        if change is None:
            continue
        total_weight += member.weight_percent
        weighted += member.weight_percent * change
    if total_weight == 0:
        return None
    return weighted / total_weight


def _weight_of(members: Sequence[Constituent]) -> Decimal:
    return sum(
        (member.weight_percent for member in members if member.change_percent is not None),
        Decimal(0),
    )


def _by_weight_desc(member: Constituent) -> tuple[Decimal, str]:
    return (-member.weight_percent, member.symbol)
