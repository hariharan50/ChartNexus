"""Breadth through a session, and the rail you pick a scope from.

Two reads behind the rebuilt Advance/Decline page.

``GetBreadthSeries`` answers "how many members were up, minute by minute" for
one index or one sector, on today or on any archived session. It is counted out
of the futures-board archive after the fact, because nothing in this
application stores breadth — see the adapter's note.

``GetSectorRail`` answers "what can I pick", and gives each row enough of a
reading to be worth picking: how many of its names are up, and the average move.

**The three tiers are the Future Lab's, word for word.** ``intraday`` is the
captured session; ``live_proxy`` is two points off the live board for a day
with nothing archived; ``empty`` means there is nothing to draw. A reader who
has learned those words on the price chart must not have to learn them again.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

from marketcompass.contexts.market_breadth.application.ports import (
    BreadthHistorySource,
    BreadthScope,
    BreadthUniverseSource,
)
from marketcompass.contexts.market_breadth.domain.breadth import SectorRow
from marketcompass.contexts.market_breadth.domain.breadth_series import (
    BreadthPoint,
    PricePoint,
    SeriesQuality,
    breadth_series,
    within_session,
)
from marketcompass.contexts.market_breadth.domain.constituents import (
    DEFAULT_DEADBAND_PERCENT,
)
from marketcompass.shared_kernel.types.identifiers import TenantId

#: Exchange-local time. India observes no DST, so a fixed offset is exact.
_IST = timezone(timedelta(hours=5, minutes=30))
_IST_OFFSET_MINUTES = 330

#: The bell, in exchange-local minutes past midnight.
SESSION_OPEN_MINUTE = 9 * 60 + 15
SESSION_CLOSE_MINUTE = 15 * 60 + 30

#: Bucket widths the page may ask for, in seconds. The same set the Future
#: Lab's price series offers — the reference design's "3m" is not here because
#: nothing else in the app has it and one page inventing a width is how two
#: charts of the same session stop lining up.
INTERVALS: dict[str, int] = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
DEFAULT_INTERVAL = "1m"

#: Below this a day is not a session, it is a reading. Two points drawn as a
#: line would imply a shape the archive does not support.
_MIN_INTRADAY_POINTS = 2

#: How many archived sessions Historical may offer. The capture worker keeps
#: thirty days; asking for more would list days that have been pruned.
MAX_SESSIONS = 30


@dataclass(frozen=True, slots=True)
class BreadthSeriesQuery:
    tenant_id: TenantId
    index: str
    #: A sector name narrows the scope to that sector of the F&O universe.
    #: ``None`` means the index itself.
    sector: str | None = None
    #: Archived session to replay. ``None`` means today — Live.
    session: date | None = None
    interval: str = DEFAULT_INTERVAL
    deadband_percent: Decimal = DEFAULT_DEADBAND_PERCENT

    @property
    def bucket_seconds(self) -> int:
        return INTERVALS.get(self.interval, INTERVALS[DEFAULT_INTERVAL])


@dataclass(frozen=True, slots=True)
class BreadthSeries:
    """One scope's session, counted."""

    label: str
    session: date
    interval: str
    points: list[BreadthPoint] = field(default_factory=list)
    quality: SeriesQuality = SeriesQuality.EMPTY
    #: How many contracts the scope covers, and how many had a baseline to be
    #: measured against. A series counted over 38 of 49 members is a weaker
    #: claim than one over all of them, and the page says so.
    universe: int = 0
    measured: int = 0
    #: ``"previous_close"`` when the broker's own figure was used, or
    #: ``"archived_close"`` when it was derived from the prior session's last
    #: capture. Never hidden: on a thin contract the two differ.
    baseline: str = "archived_close"
    #: False when the scope carries no index weights, which is every sector.
    weighted_available: bool = False
    source: str = "mock"


@dataclass(slots=True)
class GetBreadthSeries:
    history: BreadthHistorySource
    universe: BreadthUniverseSource
    #: Injected so tests pin "now" instead of racing the wall clock.
    now_utc: Callable[[], datetime] | None = None

    async def __call__(self, query: BreadthSeriesQuery) -> BreadthSeries:
        now = self._now()
        session = query.session or now.astimezone(_IST).date()
        scope = await self.universe.scope(query.index, query.sector)
        live_day = query.session is None

        if not scope.symbols:
            return BreadthSeries(label=scope.label, session=session, interval=query.interval)

        baselines = await self.history.baselines(session, scope.symbols)
        # The benchmark's own future rides in the symbol list so one query
        # fetches it with the members, but it is not a member: NIFTY is not one
        # of the fifty stocks in NIFTY. Dropping its baseline takes it out of
        # every count — the counter skips anything it cannot measure — while
        # leaving its price there to be read as the level.
        countable = _without_level(baselines, scope.level_symbol)
        points = within_session(
            await self.history.prices(session, scope.symbols),
            open_minute=SESSION_OPEN_MINUTE,
            close_minute=SESSION_CLOSE_MINUTE,
            tz_offset_minutes=_IST_OFFSET_MINUTES,
        )
        if live_day:
            # Only clip "future" captures on the live day; a past session is
            # whole by definition.
            points = [point for point in points if point.at <= now]

        series = breadth_series(
            points,
            countable,
            bucket_seconds=query.bucket_seconds,
            level_symbol=scope.level_symbol,
            weights=scope.weights or None,
            deadband_percent=query.deadband_percent,
        )

        if len(series) >= _MIN_INTRADAY_POINTS:
            return BreadthSeries(
                label=scope.label,
                session=session,
                interval=query.interval,
                points=series,
                quality=SeriesQuality.INTRADAY,
                universe=_member_count(scope),
                measured=len(countable),
                weighted_available=bool(scope.weights),
            )

        if not live_day:
            # A past day with nothing archived has no live equivalent to fall
            # back on. Saying so beats drawing today's board under its date.
            return BreadthSeries(
                label=scope.label,
                session=session,
                interval=query.interval,
                universe=_member_count(scope),
            )

        return await self._proxy(query, scope, session, now)

    async def _proxy(
        self,
        query: BreadthSeriesQuery,
        scope: BreadthScope,
        session: date,
        now: datetime,
    ) -> BreadthSeries:
        """Two points off the live board, for a day the archive has not reached.

        The honest minimum: where the scope opened and where it stands. It is a
        straight line between them and it is labelled ``live_proxy``, because
        the shape in between is exactly what this tier does not know.
        """
        reading = await self.universe.live(query.tenant_id, scope.symbols)
        countable = _without_level(reading.baselines, scope.level_symbol)
        if not reading.prices or not countable:
            return BreadthSeries(
                label=scope.label,
                session=session,
                interval=query.interval,
                universe=_member_count(scope),
            )

        # Every member at its own previous close, stamped at the bell: the
        # opening state, which is flat by construction and is the honest left
        # end of a line this tier cannot fill in.
        opening = [
            PricePoint(symbol=symbol, at=_session_open(session), price=base)
            for symbol, base in reading.baselines.items()
        ]
        points = breadth_series(
            [*opening, *reading.prices],
            countable,
            # One bucket per side: this tier has two observations and must not
            # pretend to more.
            bucket_seconds=max(int((now - _session_open(session)).total_seconds()), 1),
            level_symbol=scope.level_symbol,
            weights=scope.weights or None,
            deadband_percent=query.deadband_percent,
        )
        return BreadthSeries(
            label=scope.label,
            session=session,
            interval=query.interval,
            points=points,
            quality=SeriesQuality.LIVE_PROXY if points else SeriesQuality.EMPTY,
            universe=_member_count(scope),
            measured=len(countable),
            baseline="previous_close",
            weighted_available=bool(scope.weights),
            source=reading.source,
        )

    def _now(self) -> datetime:
        return datetime.now(UTC) if self.now_utc is None else self.now_utc()


def _without_level(
    baselines: dict[str, Decimal], level_symbol: str | None
) -> dict[str, Decimal]:
    """The baselines, minus the benchmark's own contract."""
    if level_symbol is None:
        return baselines
    return {symbol: base for symbol, base in baselines.items() if symbol != level_symbol}


def _member_count(scope: BreadthScope) -> int:
    """Contracts in the scope that are actually members of it."""
    return len(scope.symbols) - (1 if scope.level_symbol in scope.symbols else 0)


def _session_open(session: date) -> datetime:
    """09:15 IST on that session, as an aware instant."""
    return datetime(session.year, session.month, session.day, 9, 15, tzinfo=_IST).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class SectorRail:
    """What the page's left rail offers."""

    indices: tuple[str, ...] = ()
    sectors: list[SectorRow] = field(default_factory=list)
    sessions: list[date] = field(default_factory=list)
    source: str = "mock"


@dataclass(slots=True)
class GetSectorRail:
    universe: BreadthUniverseSource
    history: BreadthHistorySource
    indices: tuple[str, ...] = ()

    async def __call__(self, tenant_id: TenantId) -> SectorRail:
        board = await self.universe.sector_board(tenant_id)
        return SectorRail(
            indices=self.indices,
            sectors=board.sectors,
            # The archive decides what Historical can offer, not a calendar:
            # a day nobody captured is a day this page cannot draw.
            sessions=await self.history.sessions(MAX_SESSIONS),
            source=board.source,
        )
