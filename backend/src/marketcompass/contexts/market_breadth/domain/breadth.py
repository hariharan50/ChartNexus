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


@dataclass(frozen=True, slots=True)
class SectorRow:
    """One sector of the **F&O universe**, counted.

    Deliberately not ``SectorBreadth``. That one slices a tracked index, where
    every member carries a published index weight and the sector's move is a
    weight-average. This one covers every name with a listed future — most of
    which belong to no tracked index and therefore have no weight at all — so
    its move is a plain mean and it says so in the field name. Two aggregates
    with the same name and different arithmetic is how a page ends up quoting
    one and labelling it the other.
    """

    sector: str
    count: BreadthCount
    #: Unweighted mean move across the priced members, because there are no
    #: weights to average with. ``None`` when nothing in the sector priced.
    mean_change_percent: Decimal | None
    members: int
    #: The names themselves, biggest mover first. Carried so the page can draw
    #: a sector's members without a second board read — and so the counts above
    #: and the rows below can never come from two different reads of it.
    rows: tuple[Constituent, ...] = ()


def sector_board(
    members: Sequence[Constituent],
    *,
    deadband_percent: Decimal = DEFAULT_DEADBAND_PERCENT,
) -> list[SectorRow]:
    """Every sector across the given names, most members first.

    Sorted by size rather than by weight — the weights do not exist here, and
    ordering by move would reshuffle the list on every poll, which makes a rail
    you are trying to click impossible to use.
    """
    buckets: dict[str, list[Constituent]] = {}
    for member in members:
        buckets.setdefault(member.sector or UNCLASSIFIED, []).append(member)

    out = [
        SectorRow(
            sector=sector,
            count=count_breadth(group, deadband_percent=deadband_percent),
            mean_change_percent=mean_change(group),
            members=len(group),
            rows=tuple(sorted(group, key=_by_change_desc)),
        )
        for sector, group in buckets.items()
    ]
    out.sort(key=lambda row: (-row.members, row.sector))
    return out


def mean_change(members: Sequence[Constituent]) -> Decimal | None:
    """Plain average move across the priced members.

    For a group whose members carry no index weight, which is every sector of
    the F&O universe outside NIFTY 50 and BANK NIFTY. ``None`` rather than zero
    when nothing priced — an average with no denominator is not a flat sector.
    """
    moves = [member.change_percent for member in members if member.change_percent is not None]
    if not moves:
        return None
    return sum(moves, Decimal(0)) / Decimal(len(moves))


def weighted_breadth(members: Sequence[Constituent]) -> tuple[Decimal, Decimal]:
    """Combined index weight advancing, and declining — the weighted meter.

    The head count and this answer different questions. Twelve small names up
    against three heavyweights down is "36 advancing" and also "most of the
    index fell", and a reader watching only the count sees a rally that the
    index did not have.
    """
    advancing = declining = Decimal(0)
    for member in members:
        change = member.change_percent
        if change is None:
            continue
        if change > DEFAULT_DEADBAND_PERCENT:
            advancing += member.weight_percent
        elif change < -DEFAULT_DEADBAND_PERCENT:
            declining += member.weight_percent
    return advancing, declining


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


def _by_change_desc(member: Constituent) -> tuple[Decimal, str]:
    """Biggest gainer first, unpriced names last."""
    change = member.change_percent
    return (Decimal(0) if change is None else -change, member.symbol)


def _by_weight_desc(member: Constituent) -> tuple[Decimal, str]:
    return (-member.weight_percent, member.symbol)
