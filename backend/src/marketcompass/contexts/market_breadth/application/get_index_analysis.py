"""The four index reads: contributors, advance/decline, weightage, rotation.

Each one takes a single ``IndexConstituentSource.read`` and runs different
domain arithmetic over it. They are separate use cases rather than one
omnibus read because the pages poll independently and a page should not pay
for the three panels it is not showing — but they are deliberately built on
the same snapshot type, so a name that advanced on one is advancing on all
four.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from marketcompass.contexts.market_breadth.application.ports import IndexConstituentSource
from marketcompass.contexts.market_breadth.domain.breadth import (
    BreadthCount,
    SectorBreadth,
    breadth_by_sector,
    count_breadth,
)
from marketcompass.contexts.market_breadth.domain.constituents import (
    DEFAULT_DEADBAND_PERCENT,
    Constituent,
    IndexSnapshot,
)
from marketcompass.contexts.market_breadth.domain.contribution import (
    ContributionBoard,
    WeightSlice,
    contributions,
    weight_slices,
)
from marketcompass.contexts.market_breadth.domain.rotation import SectorPosition, positions
from marketcompass.shared_kernel.types.identifiers import TenantId

#: The index every page falls back to. NIFTY50 is the benchmark these tools
#: are read against, and the only one with a full sector spread.
DEFAULT_INDEX = "NIFTY50"


@dataclass(frozen=True, slots=True)
class IndexQuery:
    tenant_id: TenantId
    index: str = DEFAULT_INDEX
    deadband_percent: Decimal = DEFAULT_DEADBAND_PERCENT


@dataclass(frozen=True, slots=True)
class IndexHeader:
    """What every one of these pages prints above its chart.

    Carried on each result rather than fetched separately: a contributors bar
    chart whose header disagrees with its own bars about the index's move is
    the failure mode this exists to prevent.
    """

    index: str
    level: Decimal | None
    previous_close: Decimal | None
    change_absolute: Decimal | None
    change_percent: Decimal | None
    covered: int
    universe: int
    covered_weight_percent: Decimal
    source: str
    as_of: str | None
    #: "cash" or "futures" — see ``IndexSnapshot.basis``.
    basis: str

    @classmethod
    def of(cls, snapshot: IndexSnapshot) -> IndexHeader:
        return cls(
            index=snapshot.index,
            level=snapshot.level,
            previous_close=snapshot.previous_close,
            change_absolute=snapshot.change_absolute,
            change_percent=snapshot.change_percent,
            covered=len(snapshot.priced),
            universe=snapshot.universe or len(snapshot.members),
            covered_weight_percent=snapshot.covered_weight_percent,
            source=snapshot.source,
            as_of=snapshot.as_of,
            basis=snapshot.basis,
        )


@dataclass(frozen=True, slots=True)
class ContributorsResult:
    header: IndexHeader
    board: ContributionBoard


@dataclass(frozen=True, slots=True)
class AdvanceDeclineResult:
    header: IndexHeader
    overall: BreadthCount
    sectors: list[SectorBreadth] = field(default_factory=list)
    members: tuple[Constituent, ...] = ()


@dataclass(frozen=True, slots=True)
class WeightageResult:
    header: IndexHeader
    members: list[WeightSlice] = field(default_factory=list)
    sectors: list[SectorBreadth] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SectorRotationResult:
    header: IndexHeader
    sectors: list[SectorPosition] = field(default_factory=list)


@dataclass(slots=True)
class GetIndexContributors:
    source: IndexConstituentSource

    async def __call__(self, query: IndexQuery) -> ContributorsResult:
        snapshot = await self.source.read(query.tenant_id, query.index)
        return ContributorsResult(header=IndexHeader.of(snapshot), board=contributions(snapshot))


@dataclass(slots=True)
class GetAdvanceDecline:
    source: IndexConstituentSource

    async def __call__(self, query: IndexQuery) -> AdvanceDeclineResult:
        snapshot = await self.source.read(query.tenant_id, query.index)
        return AdvanceDeclineResult(
            header=IndexHeader.of(snapshot),
            overall=count_breadth(snapshot.members, deadband_percent=query.deadband_percent),
            sectors=breadth_by_sector(snapshot.members, deadband_percent=query.deadband_percent),
            # Every member, unpriced ones included: the table's job is to show
            # the index, and a row reading "—" is information.
            members=tuple(sorted(snapshot.members, key=lambda m: (-m.weight_percent, m.symbol))),
        )


@dataclass(slots=True)
class GetIndexWeightage:
    source: IndexConstituentSource

    async def __call__(self, query: IndexQuery) -> WeightageResult:
        snapshot = await self.source.read(query.tenant_id, query.index)
        return WeightageResult(
            header=IndexHeader.of(snapshot),
            # Priced members only: the donut is a share-of-index chart, and a
            # slice with no move behind it would be drawn but unexplainable.
            members=weight_slices(snapshot.priced),
            sectors=breadth_by_sector(snapshot.priced, deadband_percent=query.deadband_percent),
        )


@dataclass(slots=True)
class GetSectorRotation:
    source: IndexConstituentSource

    async def __call__(self, query: IndexQuery) -> SectorRotationResult:
        snapshot = await self.source.read(query.tenant_id, query.index)
        sectors = breadth_by_sector(snapshot.priced, deadband_percent=query.deadband_percent)
        return SectorRotationResult(
            header=IndexHeader.of(snapshot),
            sectors=positions(sectors, snapshot.change_percent),
        )
