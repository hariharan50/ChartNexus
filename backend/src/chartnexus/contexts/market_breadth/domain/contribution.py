"""How many index points each member moved the index.

The arithmetic is one line::

    points = (weight / 100) * (change% / 100) * previous index level

and everything else in this module is about being honest with it.

**Why the previous level, not the current one.** The contribution answers "of
today's move, how much was this name". Scaling by where the index *ended*
would fold part of the move being explained back into its own explanation.

**Why the weights get renormalised.** The feed does not always price every
member, and the hand-maintained weight table drifts between NSE's quarterly
rebalances. Both leave the raw weights summing to something other than 100,
which makes the contributions sum to something other than the index move — and
a Contributors page whose bars do not add up to the number in its own header
is worse than useless. So the priced members' weights are scaled to sum to 100
among themselves, and the page is told what fraction of the index that covered
(``IndexSnapshot.covered_weight_percent``) so it can say "explains 94% of the
index" instead of pretending to explain all of it.

The residual is still published rather than hidden: ``ContributionBoard.gap``
is the index's actual move minus the sum of the modelled contributions. On a
fully priced, freshly weighted index it is near zero; when it is not, that is
a fact about the data, and the page shows it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from chartnexus.contexts.market_breadth.domain.constituents import (
    Constituent,
    IndexSnapshot,
)

HUNDRED = Decimal(100)


@dataclass(frozen=True, slots=True)
class Contribution:
    """One member's push on the index, in index points."""

    symbol: str
    name: str | None
    sector: str | None
    last: Decimal
    change_percent: Decimal
    #: The renormalised weight actually used for ``points``, so a reader can
    #: check the arithmetic against the number on screen.
    weight_percent: Decimal
    points: Decimal

    @property
    def is_positive(self) -> bool:
        return self.points > 0


@dataclass(frozen=True, slots=True)
class ContributionBoard:
    """Every priced member's contribution, and how well they explain the move."""

    contributions: tuple[Contribution, ...] = ()
    #: Index points the modelled contributions account for.
    modelled_points: Decimal = Decimal(0)
    #: The index's own move in points, when it published one.
    actual_points: Decimal | None = None
    #: ``actual_points - modelled_points``. ``None`` when the index gave no
    #: level to compare against.
    gap: Decimal | None = None

    @property
    def gainers(self) -> tuple[Contribution, ...]:
        """Positive contributors, biggest push first."""
        return tuple(
            sorted(
                (row for row in self.contributions if row.points > 0),
                key=lambda row: -row.points,
            )
        )

    @property
    def losers(self) -> tuple[Contribution, ...]:
        """Negative contributors, biggest drag first."""
        return tuple(
            sorted(
                (row for row in self.contributions if row.points < 0),
                key=lambda row: row.points,
            )
        )


def normalised_weights(members: Sequence[Constituent]) -> dict[str, Decimal]:
    """Priced members' weights, scaled to sum to 100 among themselves.

    Returns an empty mapping when nothing carries weight, which the caller
    must treat as "no contributions computable" rather than dividing by it.
    """
    total = sum((member.weight_percent for member in members), Decimal(0))
    if total <= 0:
        return {}
    return {member.symbol: member.weight_percent / total * HUNDRED for member in members}


def contributions(snapshot: IndexSnapshot) -> ContributionBoard:
    """Index-point contributions for every member the feed could price."""
    priced = snapshot.priced
    baseline = snapshot.previous_close
    weights = normalised_weights(priced)
    if not priced or baseline is None or baseline <= 0 or not weights:
        return ContributionBoard(actual_points=snapshot.change_absolute)

    rows: list[Contribution] = []
    for member in priced:
        change = member.change_percent
        weight = weights.get(member.symbol)
        # `priced` guarantees a change, and `weights` is keyed off the same
        # list; the guard is for the impossible case rather than a real one.
        if change is None or weight is None:
            continue
        rows.append(
            Contribution(
                symbol=member.symbol,
                name=member.name,
                sector=member.sector,
                last=member.last,
                change_percent=change,
                weight_percent=weight,
                points=weight / HUNDRED * change / HUNDRED * baseline,
            )
        )

    modelled = sum((row.points for row in rows), Decimal(0))
    actual = snapshot.change_absolute
    return ContributionBoard(
        contributions=tuple(sorted(rows, key=lambda row: -row.points)),
        modelled_points=modelled,
        actual_points=actual,
        gap=None if actual is None else actual - modelled,
    )


@dataclass(frozen=True, slots=True)
class WeightSlice:
    """One row of the Weightage page — a member or a sector."""

    label: str
    #: Display name for a member row; ``None`` for a sector row, which is
    #: already named by ``label``.
    name: str | None
    weight_percent: Decimal
    #: Share of the *priced* index this slice represents, which is what the
    #: donut actually draws. Equal to ``weight_percent`` renormalised.
    share_percent: Decimal
    change_percent: Decimal | None
    points: Decimal | None
    members: int = 1


def weight_slices(members: Sequence[Constituent]) -> list[WeightSlice]:
    """Member rows, heaviest first, with each one's share of priced weight."""
    shares = normalised_weights(members)
    rows = [
        WeightSlice(
            label=member.symbol,
            name=member.name,
            weight_percent=member.weight_percent,
            share_percent=shares.get(member.symbol, Decimal(0)),
            change_percent=member.change_percent,
            points=None,
        )
        for member in members
    ]
    rows.sort(key=lambda row: (-row.weight_percent, row.label))
    return rows
