"""Breadth through the session, not just at this instant.

``breadth.py`` counts how many members are up right now. This counts the same
thing once per bucket across a whole trading day, which is what turns a number
into a shape: an index that rose all afternoon on *falling* advances was a
narrowing rally, and the instantaneous reading cannot say that.

**Every point is counted the same way the live meter counts.** The classifier
here is the one in ``breadth.py``, against the same deadband, so a point on the
line and the meter beside it can never disagree about whether a name moved.

**Prices are carried forward.** A contract that did not print in a given minute
has not left the index — it still holds its last price, and dropping it would
make the total member count sag wherever the tape went quiet. The count at a
bucket is therefore over *every member seen so far*, which is also why the
first bucket or two of a session can be short: the members genuinely had not
printed yet.

**Weighted and unweighted travel together.** A point carries both the head
count and the index weight behind it, because they answer different questions —
"how many names are up" versus "how much of the index is up" — and a page that
lets the reader switch between them must not have to refetch to do it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from chartnexus.contexts.market_breadth.domain.constituents import (
    DEFAULT_DEADBAND_PERCENT,
)

ZERO = Decimal(0)


class SeriesQuality(StrEnum):
    """What the numbers on a breadth chart are actually worth.

    The same three tiers the Future Lab's intraday price series uses, and
    deliberately the same words: a reader who has learned what ``live_proxy``
    means on one page must not have to learn it again on another.
    """

    #: Counted from the captured session. The real thing.
    INTRADAY = "intraday"
    #: Nothing archived for today yet, so two points: the previous close and
    #: now. A straight line between them, and the page says so.
    LIVE_PROXY = "live_proxy"
    #: Nothing to draw at all.
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class PricePoint:
    """One contract's price at one captured instant.

    This context's own shape rather than the futures archive's ``BoardFrame``:
    ``market_breadth`` may not import ``futures_analytics``, and the bridge in
    infrastructure translates. It also keeps the three fields breadth actually
    needs out of the nine the archive stores.
    """

    symbol: str
    at: datetime
    price: Decimal


@dataclass(frozen=True, slots=True)
class BreadthPoint:
    """One bucket of the session: how many were up, and how much weight."""

    at: datetime
    advancing: int
    declining: int
    unchanged: int
    #: Where the benchmark stood in this bucket, when the scope has one. A
    #: sector has no index of its own, so this is ``None`` there rather than a
    #: basket level invented to fill the column.
    level: Decimal | None = None
    #: Combined index weight of the advancing and declining members, 0-100.
    #: ``None`` when the scope carries no weights — every F&O name outside a
    #: tracked index has none, and a zero would read as "no weight advanced".
    advancing_weight: Decimal | None = None
    declining_weight: Decimal | None = None

    @property
    def net(self) -> int:
        """Advances minus declines — what an A/D line accumulates."""
        return self.advancing - self.declining


def breadth_series(
    points: Sequence[PricePoint],
    baselines: Mapping[str, Decimal],
    *,
    bucket_seconds: int,
    level_symbol: str | None = None,
    weights: Mapping[str, Decimal] | None = None,
    deadband_percent: Decimal = DEFAULT_DEADBAND_PERCENT,
) -> list[BreadthPoint]:
    """Count the scope once per bucket, oldest first.

    ``baselines`` is each symbol's previous close. A symbol with no baseline is
    left out of every count rather than treated as flat: we do not know which
    way it went, and "unchanged" is a claim.

    ``level_symbol`` names the contract whose price is the benchmark line — the
    index's own future. It is counted like any other member only if it is also
    in ``baselines``; naming it here just borrows its price for the level.
    """
    if not points or bucket_seconds <= 0:
        return []

    buckets: dict[int, dict[str, Decimal]] = {}
    for point in points:
        key = int(point.at.timestamp()) // bucket_seconds
        buckets.setdefault(key, {})[point.symbol] = point.price

    # The last instant in each bucket, so a point is stamped with a time that
    # was really observed rather than the bucket's arithmetic boundary.
    stamps: dict[int, datetime] = {}
    for point in points:
        key = int(point.at.timestamp()) // bucket_seconds
        if key not in stamps or point.at > stamps[key]:
            stamps[key] = point.at

    latest: dict[str, Decimal] = {}
    out: list[BreadthPoint] = []
    for key in sorted(buckets):
        latest.update(buckets[key])
        out.append(
            _count(
                latest,
                baselines,
                at=stamps[key],
                level=latest.get(level_symbol) if level_symbol else None,
                weights=weights,
                deadband_percent=deadband_percent,
            )
        )
    return out


def _count(
    prices: Mapping[str, Decimal],
    baselines: Mapping[str, Decimal],
    *,
    at: datetime,
    level: Decimal | None,
    weights: Mapping[str, Decimal] | None,
    deadband_percent: Decimal,
) -> BreadthPoint:
    advancing = declining = unchanged = 0
    advancing_weight = declining_weight = ZERO

    for symbol, price in prices.items():
        baseline = baselines.get(symbol)
        if baseline is None or baseline == 0:
            continue
        change = (price - baseline) / baseline * Decimal(100)
        weight = (weights or {}).get(symbol, ZERO)
        if change > deadband_percent:
            advancing += 1
            advancing_weight += weight
        elif change < -deadband_percent:
            declining += 1
            declining_weight += weight
        else:
            unchanged += 1

    return BreadthPoint(
        at=at,
        advancing=advancing,
        declining=declining,
        unchanged=unchanged,
        level=level,
        advancing_weight=advancing_weight if weights else None,
        declining_weight=declining_weight if weights else None,
    )


def within_session(
    points: Sequence[PricePoint],
    *,
    open_minute: int,
    close_minute: int,
    tz_offset_minutes: int,
) -> list[PricePoint]:
    """Drop anything captured outside the trading day's own hours.

    The broker keeps answering after the bell with the last traded price, so a
    session left unclipped grows a flat tail no trading produced — and on a
    breadth chart that tail reads as "the market stopped moving", which is a
    statement about the market rather than about the capture.
    """
    kept: list[PricePoint] = []
    for point in points:
        minutes = _local_minutes(point.at, tz_offset_minutes)
        if open_minute <= minutes <= close_minute:
            kept.append(point)
    return kept


def _local_minutes(moment: datetime, tz_offset_minutes: int) -> int:
    """Minutes past local midnight, from a UTC-aware instant."""
    shifted = moment.timestamp() + tz_offset_minutes * 60
    return int(shifted // 60) % (24 * 60)
