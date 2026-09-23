"""Institutional flow, read from NSE's own daily publications.

The live adapter the generator in ``breadth/flow_source.py`` stood in for.
Everything it serves is a file the exchange published: the participant-wise
open interest board, the FII derivative value tables, the cash-market activity
figures, and the index close for the session. Nothing the Summary page shows
is computed from anything else.

**Four documents, three formats, one session.** They are fetched
independently and assembled per session, so a day that has one and not
another renders the half it has — and the half it lacks shows as a dash,
never as a zero.

**Which days are sessions is asked, never computed.** A published file *is*
the definition of a trading session here: the date stepper walks outwards
probing for one rather than consulting a holiday calendar we would have to
maintain and would eventually get wrong.

**The cash figures have no archive.** The exchange serves FII/DII cash-market
value for the latest published session only — there is no date-addressed file
for it, unlike everything else here. So each reading is journalled in Redis as
it is seen, and the history the Cash Market chart draws is the history this
deployment has observed. That is said on the page rather than papered over by
back-filling it with something invented.

**Everything published is cached hard.** A file for a past session will never
change, so it is cached for a week; a day with no file yet is cached as absent
for half an hour, which is what keeps a page open through the evening from
hammering the archive while still noticing today's publication. Cached
globally, not per tenant: these are facts about the exchange, not about
whoever asked.

**Falls back rather than fails.** A transport failure — the archive
unreachable, a timeout, a developer offline — delegates the whole call to the
simulated source and reports ``source = "mock"``, so the badge on the page
keeps telling the truth about which of the two answered.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable
from datetime import date, timedelta, timezone
from decimal import Decimal
from typing import Any, Final, TypeVar

import httpx

from marketcompass.contexts.market_breadth.application.ports import (
    InstitutionalFlowSource,
)
from marketcompass.contexts.market_breadth.domain.constituents import IndexSnapshot
from marketcompass.contexts.market_breadth.domain.flows import (
    FlowDay,
    Participant,
    ParticipantFlow,
    Segment,
    SegmentFlow,
)
from marketcompass.contexts.market_breadth.domain.open_interest import (
    OI_SEGMENTS,
    PARTICIPANT_ORDER,
    FutureLegs,
    OiRow,
    OptionLegs,
)
from marketcompass.infrastructure.breadth.nse.participant_files import (
    BROWSER_HEADERS,
    NotPublishedError,
    OiBoard,
    cash_activity_url,
    fii_derivative_stats_url,
    flow_day,
    market_activity_url,
    parse_cash_activity,
    parse_fii_derivative_stats,
    parse_index_close,
    parse_participant_oi,
    participant_oi_url,
)
from marketcompass.infrastructure.cache.redis.client import RedisClient
from marketcompass.infrastructure.observability.structured_logging import get_logger
from marketcompass.infrastructure.time.clock import ReadableClock, SystemClock
from marketcompass.shared_kernel.types.identifiers import TenantId

log = get_logger(__name__)

T = TypeVar("T")

#: India observes no DST, so a fixed offset is exact.
_IST = timezone(timedelta(hours=5, minutes=30))

#: Saturday and Sunday as ``date.weekday()`` reports them. Weekends are skipped
#: without a request because they are the one closure that is never in doubt;
#: every other closed day is discovered by asking for its file.
_WEEKEND: Final = (5, 6)

#: How far the steppers walk before giving up, in calendar days. Comfortably
#: past the longest run the exchange closes for — a festival landing beside a
#: weekend — and short enough that a genuinely broken archive does not turn one
#: page load into a hundred requests.
_MAX_STEPS: Final = 12

#: A published file for a past session is immutable, so this is about eviction
#: pressure rather than freshness.
_PUBLISHED_TTL_SECONDS: Final = 7 * 24 * 60 * 60

#: How long "the exchange has not published this yet" is believed. Short,
#: because on any trading evening it stops being true.
_ABSENT_TTL_SECONDS: Final = 30 * 60

#: The cash endpoint carries no date in its URL and rolls over after the close,
#: so it is polled rather than archived.
_CASH_TTL_SECONDS: Final = 5 * 60

#: How long the cash journal keeps a session. Longer than any window the pages
#: can ask for, so entries age out only once they are unreachable anyway.
_JOURNAL_TTL_SECONDS: Final = 400 * 24 * 60 * 60

#: Cache value marking a session the exchange has not published.
_ABSENT: Final = "-"

_NAMESPACE: Final = "nse-flow"


class NseInstitutionalFlowSource:
    """Implements ``InstitutionalFlowSource`` against NSE's published files."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        redis: RedisClient,
        *,
        fallback: InstitutionalFlowSource,
        clock: ReadableClock | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._http = http
        self._store = _Store(redis)
        self._fallback = fallback
        self._clock = clock or SystemClock()
        self._timeout = httpx.Timeout(timeout_seconds)
        # Flipped by the first call that has to fall back. Read by `source`
        # *after* the use case has finished its reads, so the badge describes
        # the request the page is about to render rather than the last one.
        self._live = True

    @property
    def source(self) -> str:
        return "live" if self._live else "mock"

    # -- the port ------------------------------------------------------------

    async def read(
        self,
        tenant_id: TenantId,
        *,
        sessions: int,
        until: date | None = None,
    ) -> list[FlowDay]:
        try:
            return await self._read(sessions=sessions, until=until)
        except httpx.HTTPError as exc:
            return await self._degrade(
                exc, self._fallback.read(tenant_id, sessions=sessions, until=until)
            )

    async def read_open_interest(self, tenant_id: TenantId, session: date) -> list[OiRow]:
        try:
            return await self._read_open_interest(session)
        except httpx.HTTPError as exc:
            return await self._degrade(exc, self._fallback.read_open_interest(tenant_id, session))

    async def neighbours(
        self, tenant_id: TenantId, session: date
    ) -> tuple[date | None, date | None]:
        try:
            return await self._neighbours(session)
        except httpx.HTTPError as exc:
            return await self._degrade(exc, self._fallback.neighbours(tenant_id, session))

    async def read_index(
        self, tenant_id: TenantId, session: date, index: str
    ) -> IndexSnapshot | None:
        """Where the index closed on ``session``, from that day's own report.

        The broker cannot answer this: asked about a session three weeks back
        it returns the level *now*, which printed under that day's date is
        simply false. The archived report is the only honest source for it,
        and it is why the Summary page can show a level beside an archived
        session at all.
        """
        try:
            return await self._read_index(session, index)
        except httpx.HTTPError as exc:
            return await self._degrade(exc, self._fallback.read_index(tenant_id, session, index))

    # -- reads ---------------------------------------------------------------

    async def _read(self, *, sessions: int, until: date | None) -> list[FlowDay]:
        """The window, as cash journal entries plus the target day's values.

        Only the target session carries derivative value, and deliberately:
        every other day in the window exists so the cash chart and the rolling
        cash totals have a series, and fetching sixty workbooks to render one
        rail would cost sixty requests to show four numbers.
        """
        journal = await self._journal()
        # Kept fresh on every read, whichever session is on screen, so the
        # archive this deployment can draw grows while anyone is using it.
        latest_cash = await self._latest_cash()
        if latest_cash is not None:
            journal[latest_cash[0]] = latest_cash[1]

        target = until or await self._latest_session()
        if target is None:
            return []

        window = sorted(day for day in journal if day <= target)[-max(sessions, 1) :]
        if target not in window:
            window.append(target)

        derivatives = await self._derivative_values(target)
        return [
            flow_day(
                day,
                cash=journal.get(day),
                derivatives=derivatives if day == target else None,
            )
            for day in window
        ]

    async def _read_open_interest(self, session: date) -> list[OiRow]:
        today = await self._board(session)
        if today is None:
            return []

        previous, _ = await self._neighbours(session)
        # Falling back to today's board makes every change read zero, which is
        # the honest rendering of "there is no previous session to compare
        # against" — the first day of the archive, or a stepper at its end.
        yesterday = (await self._board(previous) if previous else None) or today

        return [
            OiRow(
                participant=participant,
                segment=segment,
                net=today[(participant, segment)].net,
                previous_net=yesterday[(participant, segment)].net,
                legs=today[(participant, segment)],
            )
            for participant in PARTICIPANT_ORDER
            for segment in OI_SEGMENTS
        ]

    async def _neighbours(self, session: date) -> tuple[date | None, date | None]:
        latest = await self._latest_session()
        previous = await self._step(session, -1)
        # Nothing is published for a session that has not happened yet, so the
        # forward arrow stops at the latest published day rather than walking
        # into a future the archive cannot contain.
        following = await self._step(session, 1) if latest and session < latest else None
        return previous, following

    async def _read_index(self, session: date, index: str) -> IndexSnapshot | None:
        cached = await self._store.get("index", session.isoformat(), index)
        if cached == _ABSENT:
            return None
        if cached is None:
            try:
                payload = await self._fetch(market_activity_url(session))
                close, previous = parse_index_close(payload, index=index)
            except NotPublishedError as exc:
                log.debug("nse_index_absent", session=str(session), index=index, reason=str(exc))
                await self._store.set(
                    _ABSENT, _ABSENT_TTL_SECONDS, "index", session.isoformat(), index
                )
                return None
            cached = json.dumps([str(close), str(previous)])
            await self._store.set(
                cached, _PUBLISHED_TTL_SECONDS, "index", session.isoformat(), index
            )

        level, prior = (Decimal(value) for value in json.loads(cached))
        return IndexSnapshot(
            index=index,
            level=level,
            previous_close=prior,
            source="live",
            as_of=session.isoformat(),
            basis="cash",
        )

    # -- the calendar --------------------------------------------------------

    async def _latest_session(self) -> date | None:
        """The most recent day the participant file exists for."""
        cursor = self._today()
        for _ in range(_MAX_STEPS):
            if cursor.weekday() not in _WEEKEND and await self._board(cursor) is not None:
                return cursor
            cursor -= timedelta(days=1)
        return None

    async def _step(self, session: date, direction: int) -> date | None:
        """The nearest published session in one direction, or ``None``."""
        cursor = session + timedelta(days=direction)
        for _ in range(_MAX_STEPS):
            if cursor.weekday() not in _WEEKEND and await self._board(cursor) is not None:
                return cursor
            cursor += timedelta(days=direction)
        return None

    def _today(self) -> date:
        """The exchange's date, not the server's.

        A process running in UTC rolls over at 05:30 IST, which would have it
        looking for a file hours before the session it names has opened.
        """
        return self._clock.now().astimezone(_IST).date()

    # -- the four documents --------------------------------------------------

    async def _board(self, session: date) -> OiBoard | None:
        """One session's open interest board, or ``None`` if unpublished."""
        cached = await self._store.get("oi", session.isoformat())
        if cached == _ABSENT:
            return None
        if cached is not None:
            return _decode_board(cached)

        try:
            payload = await self._fetch(participant_oi_url(session))
            board = parse_participant_oi(payload, session=session)
        except NotPublishedError as exc:
            log.debug("nse_participant_oi_absent", session=str(session), reason=str(exc))
            await self._store.set(_ABSENT, _ABSENT_TTL_SECONDS, "oi", session.isoformat())
            return None

        await self._store.set(
            _encode_board(board), _PUBLISHED_TTL_SECONDS, "oi", session.isoformat()
        )
        return board

    async def _derivative_values(self, session: date) -> dict[Segment, ParticipantFlow] | None:
        """FII buy and sell value per derivative segment, in rupees crore."""
        cached = await self._store.get("stats", session.isoformat())
        if cached == _ABSENT:
            return None
        if cached is None:
            try:
                payload = await self._fetch(fii_derivative_stats_url(session))
                flows = parse_fii_derivative_stats(payload, session=session)
            except NotPublishedError as exc:
                log.debug("nse_fii_stats_absent", session=str(session), reason=str(exc))
                await self._store.set(_ABSENT, _ABSENT_TTL_SECONDS, "stats", session.isoformat())
                return None
            cached = json.dumps(
                {segment.value: [str(flow.buy), str(flow.sell)] for segment, flow in flows.items()}
            )
            await self._store.set(cached, _PUBLISHED_TTL_SECONDS, "stats", session.isoformat())

        return {
            Segment(name): ParticipantFlow(buy=Decimal(buy), sell=Decimal(sell))
            for name, (buy, sell) in json.loads(cached).items()
        }

    async def _latest_cash(self) -> tuple[date, SegmentFlow] | None:
        """The cash-market session the endpoint is currently answering for.

        Journalled on the way past: it is the only reading of this figure that
        will ever be available for that day.
        """
        cached = await self._store.get("cash-latest")
        if cached == _ABSENT:
            return None
        if cached is None:
            try:
                payload = await self._fetch(cash_activity_url())
                session, flow = parse_cash_activity(payload)
            except NotPublishedError as exc:
                log.debug("nse_cash_activity_absent", reason=str(exc))
                await self._store.set(_ABSENT, _ABSENT_TTL_SECONDS, "cash-latest")
                return None
            cached = json.dumps([session.isoformat(), _encode_cash(flow)])
            await self._store.set(cached, _CASH_TTL_SECONDS, "cash-latest")
            await self._journal_write(session, flow)

        iso, encoded = json.loads(cached)
        return date.fromisoformat(iso), _decode_cash(encoded)

    # -- the cash journal ----------------------------------------------------

    async def _journal(self) -> dict[date, SegmentFlow]:
        raw = await self._store.hgetall("cash-journal")
        entries: dict[date, SegmentFlow] = {}
        for iso, encoded in raw.items():
            try:
                entries[date.fromisoformat(iso)] = _decode_cash(json.loads(encoded))
            except (ValueError, KeyError, TypeError):
                # One unreadable entry is not worth losing the series over;
                # it simply drops out and is rewritten the next time it is
                # observed, which for the latest session is within minutes.
                log.warning("nse_cash_journal_entry_unreadable", session=iso)
        return entries

    async def _journal_write(self, session: date, flow: SegmentFlow) -> None:
        await self._store.hset(
            "cash-journal",
            session.isoformat(),
            json.dumps(_encode_cash(flow)),
            _JOURNAL_TTL_SECONDS,
        )

    # -- plumbing ------------------------------------------------------------

    async def _fetch(self, url: str) -> bytes:
        response = await self._http.get(
            url, headers=BROWSER_HEADERS, timeout=self._timeout, follow_redirects=True
        )
        if response.status_code == httpx.codes.NOT_FOUND:
            # The `www` host answers an unpublished day with a real 404; the
            # archive host answers with an HTML page under a 200, which the
            # parsers catch. Both mean the same thing here.
            raise NotPublishedError(f"404 for {url}")
        response.raise_for_status()
        return response.content

    async def _degrade(self, exc: httpx.HTTPError, fallback: Awaitable[T]) -> T:
        """Hand the call to the generator, and say so on the badge."""
        if self._live:
            log.warning("nse_flow_source_unreachable", error=repr(exc))
        self._live = False
        return await fallback


# -- encoding ------------------------------------------------------------------
#
# Cache payloads are written by hand rather than pickled so that a change to a
# domain dataclass cannot silently deserialise into the wrong shape a week
# later, when the entry written before the change is still in Redis.


def _encode_board(board: OiBoard) -> str:
    return json.dumps(
        {
            f"{participant.value}|{segment.value}": _encode_legs(legs)
            for (participant, segment), legs in board.items()
        }
    )


def _encode_legs(legs: FutureLegs | OptionLegs) -> list[int]:
    if isinstance(legs, FutureLegs):
        return [legs.long, legs.short]
    return [legs.call_long, legs.call_short, legs.put_long, legs.put_short]


#: How many legs a futures book encodes as, which is what tells the two kinds
#: of cached leg apart on the way back in. Options encode as four.
_FUTURE_LEG_COUNT: Final = 2


def _decode_board(payload: str) -> OiBoard:
    board: OiBoard = {}
    for key, legs in json.loads(payload).items():
        participant, _, segment = key.partition("|")
        board[(Participant(participant), Segment(segment))] = (
            FutureLegs(long=legs[0], short=legs[1])
            if len(legs) == _FUTURE_LEG_COUNT
            else OptionLegs(
                call_long=legs[0], call_short=legs[1], put_long=legs[2], put_short=legs[3]
            )
        )
    return board


def _encode_cash(flow: SegmentFlow) -> dict[str, str | None]:
    return {
        "fb": str(flow.fii.buy),
        "fs": str(flow.fii.sell),
        "db": None if flow.dii is None else str(flow.dii.buy),
        "ds": None if flow.dii is None else str(flow.dii.sell),
    }


def _decode_cash(encoded: dict[str, str | None]) -> SegmentFlow:
    buy, sell = encoded["db"], encoded["ds"]
    return SegmentFlow(
        segment=Segment.CASH,
        fii=ParticipantFlow(buy=Decimal(str(encoded["fb"])), sell=Decimal(str(encoded["fs"]))),
        # Absent rather than zero: a session where the DII line was not
        # published is not a session where domestic institutions did nothing.
        dii=None
        if buy is None or sell is None
        else ParticipantFlow(buy=Decimal(buy), sell=Decimal(sell)),
    )


class _Store:
    """The Redis calls this adapter makes, with failures demoted to misses.

    A cache outage should cost latency, not the page: every read returns
    ``None`` and every write is dropped, which degrades to fetching each file
    on every request rather than to an error.
    """

    def __init__(self, redis: RedisClient) -> None:
        self._redis = redis

    def _client(self) -> Any:
        """The Redis client, untyped.

        redis-py declares its commands as ``Awaitable[T] | T`` so one class can
        serve both the sync and async APIs. That union is not awaitable as far
        as the type checker is concerned, and the alternative is a cast at
        every call site — the same accommodation ``RedisOpenInterestCache``
        makes.
        """
        return self._redis.client

    async def get(self, *parts: str) -> str | None:
        try:
            raw = await self._client().get(self._redis.key(_NAMESPACE, *parts))
        except Exception as exc:
            log.warning("nse_flow_cache_read_failed", error=repr(exc))
            return None
        return None if raw is None else _text(raw)

    async def set(self, value: str, ttl_seconds: int, *parts: str) -> None:
        try:
            await self._client().set(self._redis.key(_NAMESPACE, *parts), value, ex=ttl_seconds)
        except Exception as exc:
            log.warning("nse_flow_cache_write_failed", error=repr(exc))

    async def hgetall(self, *parts: str) -> dict[str, str]:
        try:
            raw = await self._client().hgetall(self._redis.key(_NAMESPACE, *parts))
        except Exception as exc:
            log.warning("nse_flow_cache_read_failed", error=repr(exc))
            return {}
        return {_text(key): _text(value) for key, value in (raw or {}).items()}

    async def hset(self, name: str, field: str, value: str, ttl_seconds: int) -> None:
        try:
            key = self._redis.key(_NAMESPACE, name)
            client = self._client()
            await client.hset(key, field, value)
            await client.expire(key, ttl_seconds)
        except Exception as exc:
            log.warning("nse_flow_cache_write_failed", error=repr(exc))


def _text(value: object) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)
