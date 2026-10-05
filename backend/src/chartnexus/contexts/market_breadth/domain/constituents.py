"""The reading one index member contributes to every page in this context.

Four of the six Analysis pages — Contributors, Advance/Decline, Weightage and
Sector Rotation — are different arithmetic over the *same* list of index
members priced against their previous close. Defining that list once, here,
is what keeps a stock from advancing on one page and declining on another.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

#: Below this, a move is rounding rather than direction, and the member counts
#: as unchanged. Matches the futures board's deadband so the two never disagree
#: about whether a name moved.
DEFAULT_DEADBAND_PERCENT = Decimal("0.05")


@dataclass(frozen=True, slots=True)
class Constituent:
    """One index member, priced, with the weight it carries in the index.

    ``weight_percent`` is free-float market-capitalisation weight as a
    percentage of the whole index, from the catalog's hand-maintained table.
    It is *not* derived from the price here — index weights are rebalanced
    quarterly against a divisor this application does not have — so a stale
    table shows up as a contribution that is slightly off, never as a wrong
    direction.
    """

    symbol: str
    name: str | None
    last: Decimal
    previous_close: Decimal | None
    weight_percent: Decimal
    sector: str | None = None

    @property
    def change_percent(self) -> Decimal | None:
        """Day-over-day move, or ``None`` when there is no baseline.

        ``None`` is a real answer — a newly listed member, or a feed that gave
        a price and no prior close — and callers must render it as "no data"
        rather than as a flat 0.00%.
        """
        prior = self.previous_close
        if prior is None or prior == 0:
            return None
        return (self.last - prior) / prior * Decimal(100)

    @property
    def change_absolute(self) -> Decimal | None:
        prior = self.previous_close
        return None if prior is None else self.last - prior


@dataclass(frozen=True, slots=True)
class IndexSnapshot:
    """An index, its members, and where the numbers came from.

    ``level`` and ``previous_close`` are the index's own prints, not a sum over
    the members: the two differ by the index divisor and by whatever members
    the feed could not price, and showing a reconstructed level as if it were
    the published one is the kind of quiet lie this codebase does not tell.
    """

    index: str
    level: Decimal | None
    previous_close: Decimal | None
    members: tuple[Constituent, ...] = ()
    #: How many names the index holds, against how many were priced. A board
    #: covering 38 of 50 is a weaker claim than one covering all of them.
    universe: int = 0
    #: "live" or "mock" — never let the two be mistaken for each other.
    source: str = "mock"
    #: When the underlying prints were taken, ISO-8601, or ``None`` if unknown.
    as_of: str | None = None
    #: Which market the member prices came from: ``"cash"`` for equity prints,
    #: ``"futures"`` for the front-month contract.
    #:
    #: Carried because it changes what the numbers mean, slightly but really.
    #: A future's day-over-day percentage tracks its underlying closely and
    #: diverges with the basis — carry, dividends, and the roll. Close enough
    #: to rank contributors and count breadth; not the same number, so the
    #: page says which one it is rather than letting a reader assume.
    basis: str = "cash"

    @property
    def change_percent(self) -> Decimal | None:
        prior = self.previous_close
        if prior is None or prior == 0 or self.level is None:
            return None
        return (self.level - prior) / prior * Decimal(100)

    @property
    def change_absolute(self) -> Decimal | None:
        if self.level is None or self.previous_close is None:
            return None
        return self.level - self.previous_close

    @property
    def priced(self) -> tuple[Constituent, ...]:
        """Members with a usable percentage change."""
        return tuple(member for member in self.members if member.change_percent is not None)

    @property
    def covered_weight_percent(self) -> Decimal:
        """Index weight the priced members account for.

        The honest denominator for anything expressed as a share of the index.
        If it reads 82%, then a "sector weight" on the page is 82% of the index
        being described, and the page says so.
        """
        return sum((member.weight_percent for member in self.priced), Decimal(0))
