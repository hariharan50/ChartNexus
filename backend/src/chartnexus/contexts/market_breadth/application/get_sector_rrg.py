"""Every sector's rotation against the benchmark, as a Relative Rotation Graph.

**What makes this possible at all.** The futures board is archived minute by
minute for the whole F&O universe, which is the only multi-period price history
this application keeps. The older sector-rotation board could not draw a tail
and said so in its own docstring; it read one live snapshot. This reads the
archive instead, so the second axis is genuine momentum rather than a
single-session stand-in.

**Sectors have no index, so one is built.** There is no tradeable NIFTY IT in
the catalog — the symbol master lists index derivatives and stock futures, not
sector indices — so each sector's level is an equal-weighted composite of its
own members. ``BreadthScope`` carries no weights for a sector, so equal is the
only honest weighting available; see
:func:`~chartnexus.contexts.market_breadth.domain.rrg.composite`.

**Periods are buckets, not calendar time.** Sessions are concatenated in order
and the overnight gap is simply not a period. An RRG cares about the *sequence*
of observations, not their spacing, so the gap between two sessions is no
different from the gap between two consecutive buckets — and pricing it would
put a phantom move in every sector at the same instant.

**The window is tuned per interval, not shared.** A fourteen-period z-score is
right on fifteen-minute buckets, where a session is twenty-five of them, and
impossible on a daily axis the archive caps at thirty sessions — it would need
thirty-five. Each interval therefore carries its own tuning, and
:func:`periods_required` derives the minimum from it rather than restating a
number that would drift.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal

from chartnexus.contexts.market_breadth.application.get_breadth_series import (
    MAX_SESSIONS,
    SESSION_CLOSE_MINUTE,
    SESSION_OPEN_MINUTE,
)
from chartnexus.contexts.market_breadth.application.ports import (
    BreadthHistorySource,
    BreadthUniverseSource,
)
from chartnexus.contexts.market_breadth.domain.breadth_series import within_session
from chartnexus.contexts.market_breadth.domain.rrg import (
    DEFAULT_TAIL,
    RrgTail,
    composite,
    rotation,
)
from chartnexus.shared_kernel.types.identifiers import TenantId

_IST_OFFSET_MINUTES = 330

DAILY = "1d"


@dataclass(frozen=True, slots=True)
class Tuning:
    """One interval's statistics, and the bucket it measures over.

    ``bucket_seconds`` is ``None`` for the daily axis, where a period is a
    whole session rather than a slice of one.
    """

    bucket_seconds: int | None
    window: int
    smoothing: int
    momentum_span: int


#: Per-interval tuning. The windows shorten as the bucket widens because the
#: archive is a fixed thirty sessions: at fifteen minutes that is seven hundred
#: periods and a long window is free, while at daily it is thirty periods total
#: and a fourteen-period window could never produce a single point.
TUNING: dict[str, Tuning] = {
    "15m": Tuning(bucket_seconds=900, window=14, smoothing=3, momentum_span=4),
    "1h": Tuning(bucket_seconds=3600, window=8, smoothing=2, momentum_span=3),
    DAILY: Tuning(bucket_seconds=None, window=5, smoothing=2, momentum_span=2),
}

INTERVALS: tuple[str, ...] = ("15m", "1h", DAILY)

#: Intraday by default. The daily axis needs thirteen archived sessions before
#: it can draw anything, so defaulting to it would show most deployments an
#: empty board on first load.
DEFAULT_INTERVAL = "15m"

#: Sessions to reach back over. The archive prunes at thirty, so asking for
#: more would list days that are gone.
DEFAULT_SESSIONS = MAX_SESSIONS

#: A symbol must cover at least this much of the grid to join its sector's
#: composite. One name that listed halfway through the window would otherwise
#: truncate every other member back to its own first print — see :func:`_align`.
_MIN_COVERAGE = 0.75


def periods_required(tuning: Tuning) -> int:
    """Periods the pipeline consumes before a single point can exist.

    Both axes are normalised over ``window`` and smoothed, and momentum reaches
    back a further span between them — so the window is paid twice, once for
    the ratio and once for the momentum of that ratio. Working it through::

        ratio      = N - window - smoothing + 2
        momentum   = ratio - momentum_span
        axis       = momentum - window - smoothing + 2

    and setting ``axis >= 1`` gives the expression below. Derived rather than
    written as a number so it cannot drift away from the tuning it comes from.
    """
    return 2 * tuning.window + 2 * tuning.smoothing + tuning.momentum_span - 3


@dataclass(frozen=True, slots=True)
class SectorRrgQuery:
    tenant_id: TenantId
    #: The index whose future is the benchmark every sector is measured against.
    index: str
    interval: str = DEFAULT_INTERVAL
    tail: int = DEFAULT_TAIL
    sessions: int = DEFAULT_SESSIONS

    @property
    def tuning(self) -> Tuning:
        return TUNING.get(self.interval, TUNING[DEFAULT_INTERVAL])


@dataclass(frozen=True, slots=True)
class SectorRrgResult:
    """The board: one tail per sector, plus what it was measured over."""

    benchmark: str
    interval: str
    tails: list[RrgTail] = field(default_factory=list)
    #: Sessions the window spans, oldest first.
    sessions: list[date] = field(default_factory=list)
    #: Periods on the grid, before the window and smoothing took their share.
    #: The page uses it to explain an empty board: "24 periods, 35 needed" is a
    #: different problem from "no sector could be priced", and the two are
    #: fixed by different things.
    periods: int = 0
    periods_required: int = 0
    window: int = 0
    source: str = "mock"


@dataclass(slots=True)
class GetSectorRrg:
    history: BreadthHistorySource
    universe: BreadthUniverseSource

    async def __call__(self, query: SectorRrgQuery) -> SectorRrgResult:
        tuning = query.tuning
        sessions = sorted(await self.history.sessions(query.sessions))
        board = await self.universe.sector_board(query.tenant_id)
        scope = await self.universe.scope(query.index, None)

        def empty(periods: int = 0) -> SectorRrgResult:
            return SectorRrgResult(
                benchmark=scope.label,
                interval=query.interval,
                sessions=sessions,
                periods=periods,
                periods_required=periods_required(tuning),
                window=tuning.window,
                source=board.source,
            )

        if not sessions or not board.sectors or scope.level_symbol is None:
            return empty()

        members = {row.sector: tuple(item.symbol for item in row.rows) for row in board.sectors}
        wanted = sorted({symbol for names in members.values() for symbol in names})
        if not wanted:
            return empty()

        grid, stamps = await self._grid(
            sessions, (*wanted, scope.level_symbol), tuning.bucket_seconds
        )
        if not stamps:
            return empty()

        tails = [
            tail
            for row in board.sectors
            if (
                tail := self._tail(
                    row.sector,
                    members[row.sector],
                    grid=grid,
                    stamps=stamps,
                    benchmark_symbol=scope.level_symbol,
                    query=query,
                )
            )
            is not None
        ]
        return SectorRrgResult(
            benchmark=scope.label,
            interval=query.interval,
            tails=tails,
            sessions=sessions,
            periods=len(stamps),
            periods_required=periods_required(tuning),
            window=tuning.window,
            source=board.source,
        )

    def _tail(
        self,
        sector: str,
        symbols: Sequence[str],
        *,
        grid: dict[str, list[Decimal | None]],
        stamps: Sequence[datetime],
        benchmark_symbol: str,
        query: SectorRrgQuery,
    ) -> RrgTail | None:
        """One sector's path, or ``None`` when it could not be measured.

        A sector that cannot be plotted is dropped rather than returned empty:
        a row on the page's symbol list that never appears on the grid is one
        the reader keeps clicking to no effect.
        """
        aligned = _align(
            [grid[symbol] for symbol in symbols if symbol in grid],
            grid[benchmark_symbol],
        )
        if aligned is None:
            return None
        series, benchmark = aligned

        level = composite(series)
        if not level:
            return None

        points = rotation(
            level,
            benchmark,
            stamps[-len(benchmark) :],
            window=query.tuning.window,
            smoothing=query.tuning.smoothing,
            momentum_span=query.tuning.momentum_span,
            tail=query.tail,
        )
        if not points:
            return None
        return RrgTail(sector=sector, points=points, measured=len(series), members=len(symbols))

    async def _grid(
        self,
        sessions: Sequence[date],
        symbols: Sequence[str],
        bucket_seconds: int | None,
    ) -> tuple[dict[str, list[Decimal | None]], list[datetime]]:
        """Every symbol's price on one shared period grid, oldest period first.

        ``None`` marks a period a symbol did not print in. The gap is left
        visible here rather than filled inline so :func:`_align` can tell a
        symbol that was quiet for a bucket from one that had not started
        printing yet — a forward fill applied here would silently turn the
        second into a flat line at a price it never traded.

        Period keys are globally ordered without needing a per-session offset:
        an epoch bucket already encodes its date, and the daily axis keys on
        the session's ordinal.
        """
        columns: dict[int, dict[str, Decimal]] = {}

        for session in sessions:
            points = within_session(
                await self.history.prices(session, symbols),
                open_minute=SESSION_OPEN_MINUTE,
                close_minute=SESSION_CLOSE_MINUTE,
                tz_offset_minutes=_IST_OFFSET_MINUTES,
            )
            for point in sorted(points, key=lambda item: item.at):
                key = (
                    session.toordinal()
                    if bucket_seconds is None
                    else int(point.at.timestamp()) // bucket_seconds
                )
                # Last write wins, so a bucket holds its close rather than its
                # open — which is what a period's price means everywhere else.
                columns.setdefault(key, {})[point.symbol] = point.price

        order = sorted(columns)
        stamps = [_stamp(key, bucket_seconds) for key in order]
        grid: dict[str, list[Decimal | None]] = {
            symbol: [columns[key].get(symbol) for key in order] for symbol in symbols
        }
        return grid, stamps


def _align(
    members: Sequence[Sequence[Decimal | None]],
    benchmark: Sequence[Decimal | None],
) -> tuple[list[list[Decimal]], list[Decimal]] | None:
    """Trim a sector and its benchmark to one common, fully-priced window.

    Every series here ends on the same period but they do not all *start* on
    one: a symbol only enters the grid at its first print. Trimming each list
    to the shortest would align them at the left and leave them staggered at
    the right, which plots one member's Tuesday against another's Thursday —
    the bug this function exists to make impossible.

    So the common start is the latest first-print among the members that cover
    enough of the grid to be worth keeping, and everything is sliced from
    there. Members below :data:`_MIN_COVERAGE` are dropped instead of allowed
    to truncate the rest: one name that listed late should cost the sector that
    name, not most of its history.
    """
    span = len(benchmark)
    if span == 0:
        return None

    benchmark_start = _first_print(benchmark)
    if benchmark_start is None:
        return None

    starts: list[tuple[int, Sequence[Decimal | None]]] = []
    for series in members:
        start = _first_print(series)
        if start is None:
            continue
        if (span - start) / span < _MIN_COVERAGE:
            continue
        starts.append((start, series))

    if not starts:
        return None

    begin = max(benchmark_start, *(start for start, _ in starts))
    filled = [_fill(series[begin:]) for _, series in starts]
    filled = [series for series in filled if series]
    if not filled:
        return None
    return filled, _fill(benchmark[begin:])


def _first_print(series: Sequence[Decimal | None]) -> int | None:
    for index, value in enumerate(series):
        if value is not None:
            return index
    return None


def _fill(series: Sequence[Decimal | None]) -> list[Decimal]:
    """Carry each price forward over the periods its symbol stayed quiet.

    The caller has already sliced to a period the symbol had printed by, so
    there is no leading gap left to invent a price for.
    """
    out: list[Decimal] = []
    last: Decimal | None = None
    for value in series:
        if value is not None:
            last = value
        if last is not None:
            out.append(last)
    return out


def _stamp(key: int, bucket_seconds: int | None) -> datetime:
    """The instant a period is labelled with, always timezone-aware."""
    if bucket_seconds is None:
        # Daily: the session's own date, stamped at the close.
        return datetime.combine(date.fromordinal(key), time(15, 30), tzinfo=UTC)
    return datetime.fromtimestamp(key * bucket_seconds, tz=UTC)
