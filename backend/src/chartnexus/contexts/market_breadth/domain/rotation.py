"""Where each sector sits relative to the index it belongs to.

A relative-rotation read, drawn on two axes a single session's board can
actually support:

* **x — relative strength.** The sector's weight-averaged move minus the
  index's own move. Positive means the sector is pulling the index up harder
  than the index is rising (or falling less than it is falling).
* **y — participation.** The share of the sector's members that advanced,
  re-centred on 50 so zero means "half the sector took part".

**This is not a classical RRG and the page must not imply that it is.** A true
relative-rotation graph plots RS-Ratio against RS-*Momentum* — the rate of
change of relative strength — and traces a multi-week tail through the
quadrants. That needs weeks of stored constituent history, which this
application does not keep yet. Participation is a defensible stand-in for one
session: a sector led by one heavyweight while the rest of it sinks is a
different animal from one where everything is bid, and that distinction is
exactly what the second axis exists to expose. It is a snapshot, so there is
no tail, and the labels say "participation" rather than "momentum".

The quadrant names are kept from the RRG convention because they carry the
right meaning here: strength with participation is *leading*, participation
without strength yet is *improving*, strength without participation is
*weakening*, neither is *lagging*.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from chartnexus.contexts.market_breadth.domain.breadth import SectorBreadth

#: The participation axis is centred here: half the sector advancing is the
#: neutral reading, not zero.
NEUTRAL_PARTICIPATION = Decimal(50)

#: Relative strength inside this band is called flat rather than a direction.
#: A sector 0.02% ahead of the index has not decoupled from it.
STRENGTH_DEADBAND = Decimal("0.05")


class Quadrant(StrEnum):
    LEADING = "leading"
    IMPROVING = "improving"
    WEAKENING = "weakening"
    LAGGING = "lagging"


@dataclass(frozen=True, slots=True)
class SectorPosition:
    """One plotted sector."""

    sector: str
    #: Weight-averaged move of the sector's priced members.
    change_percent: Decimal
    #: ``change_percent`` minus the index's move — the x axis.
    relative_strength: Decimal
    #: Share of priced members advancing, 0-100.
    participation_percent: Decimal
    #: ``participation_percent - 50`` — the y axis, so the origin is neutral.
    participation_offset: Decimal
    #: Combined index weight, which sizes the bubble. A 28%-weight sector
    #: drifting matters more than a 0.8% one sprinting.
    weight_percent: Decimal
    advancing: int
    declining: int
    members: int
    quadrant: Quadrant
    #: The sector's biggest positive and negative movers by weight, for the
    #: hover card. Symbols only — the page already has the full rows.
    leaders: tuple[str, ...] = ()
    laggards: tuple[str, ...] = ()


def classify(relative_strength: Decimal, participation_percent: Decimal) -> Quadrant:
    """Which quadrant a (strength, participation) pair lands in.

    The deadband applies to strength only. Participation is a count-derived
    percentage with no comparable noise floor — 6 of 12 advancing is exactly
    neutral, and 7 of 12 is a real majority, not a rounding artefact.
    """
    strong = relative_strength > STRENGTH_DEADBAND
    broad = participation_percent > NEUTRAL_PARTICIPATION
    if strong and broad:
        return Quadrant.LEADING
    if broad:
        return Quadrant.IMPROVING
    if strong:
        return Quadrant.WEAKENING
    return Quadrant.LAGGING


def positions(
    sectors: Sequence[SectorBreadth],
    index_change_percent: Decimal | None,
) -> list[SectorPosition]:
    """Place every sector that could be priced, heaviest first.

    ``index_change_percent`` of ``None`` means the index gave no move to
    measure against; the sectors are then plotted against zero, which is the
    same chart with a weaker claim, and the caller says so on the page.
    """
    baseline = index_change_percent or Decimal(0)
    out: list[SectorPosition] = []

    for sector in sectors:
        change = sector.weighted_change_percent
        counted = sector.count.counted
        if change is None or counted == 0:
            continue
        participation = Decimal(sector.count.advancing) / Decimal(counted) * Decimal(100)
        relative = change - baseline
        out.append(
            SectorPosition(
                sector=sector.sector,
                change_percent=change,
                relative_strength=relative,
                participation_percent=participation,
                participation_offset=participation - NEUTRAL_PARTICIPATION,
                weight_percent=sector.weight_percent,
                advancing=sector.count.advancing,
                declining=sector.count.declining,
                members=counted,
                quadrant=classify(relative, participation),
                leaders=_movers(sector, positive=True),
                laggards=_movers(sector, positive=False),
            )
        )

    out.sort(key=lambda entry: (-entry.weight_percent, entry.sector))
    return out


#: How many names the hover card names on each side. Three fits the card and is
#: enough to say *who* moved the sector.
_MOVER_LIMIT = 3


def _movers(sector: SectorBreadth, *, positive: bool) -> tuple[str, ...]:
    scored = [
        (member.symbol, member.change_percent)
        for member in sector.members
        if member.change_percent is not None
        and (member.change_percent > 0 if positive else member.change_percent < 0)
    ]
    scored.sort(key=lambda entry: -entry[1] if positive else entry[1])
    return tuple(symbol for symbol, _ in scored[:_MOVER_LIMIT])
