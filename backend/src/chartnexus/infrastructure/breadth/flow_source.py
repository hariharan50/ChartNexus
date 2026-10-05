"""Institutional flow, generated.

Implements ``InstitutionalFlowSource``. **There is no live adapter yet**, and
this file is the honest placeholder for one.

The numbers come from NSE's daily participant-wise trading file, which no
broker API serves: it is a CSV published on the exchange's own site after the
close, and wiring it up means a scheduled fetch, a parser, and somewhere to
store the history — a piece of work in its own right, deliberately not
smuggled into this feature. Until then the pages need *something* shaped like
the real thing so the layout, the scales and the sign conventions can be
built and reviewed.

Three rules make that safe:

* **Every reading is stamped ``source = "mock"``**, the port declares that
  property, and each page renders the Simulated badge. A generated flow board
  is indistinguishable from a true one by eye; this is the only thing that
  separates them.
* **It is deterministic in the session date.** The same day always generates
  the same figures, so a page does not reshuffle its own history on every
  poll, and a screenshot stays reproducible.
* **Nothing is persisted.** These figures never reach a table, so they can
  never be mistaken later for an archived observation.

The shapes are drawn from how the real series behaves — FII and DII cash nets
are strongly negatively correlated, index options carry an order of magnitude
more turnover than cash, and derivative segments publish no DII line — because
a placeholder that behaves nothing like the real data teaches the layout the
wrong lessons.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from math import pi, sin
from random import Random

from chartnexus.contexts.market_breadth.domain.flows import (
    FlowDay,
    Participant,
    ParticipantFlow,
    Segment,
    SegmentFlow,
)
from chartnexus.contexts.market_breadth.domain.open_interest import (
    OI_SEGMENTS,
    PARTICIPANT_ORDER,
    FutureLegs,
    OiRow,
    OptionLegs,
)
from chartnexus.infrastructure.brokers.mock.quote_factory import in_ist
from chartnexus.infrastructure.time.clock import ReadableClock, SystemClock
from chartnexus.shared_kernel.types.identifiers import TenantId

#: Saturday and Sunday as ``date.weekday()`` reports them.
_WEEKEND = (5, 6)

#: Typical gross turnover per side, in rupees crore, per segment. Ranges, not
#: points, so consecutive sessions differ the way real ones do.
_TURNOVER: dict[Segment, tuple[int, int]] = {
    Segment.CASH: (9_000, 17_000),
    Segment.INDEX_FUTURES: (6_000, 13_000),
    Segment.INDEX_OPTIONS: (60_000, 180_000),
    Segment.STOCK_FUTURES: (12_000, 24_000),
    Segment.STOCK_OPTIONS: (18_000, 40_000),
}

#: How far a segment's net strays from flat, as a fraction of its gross. Cash
#: nets are a small slice of a large turnover — a ₹2,000 crore net on ₹14,000
#: crore bought is a *big* day — and a generator that ignores that produces
#: nets nobody has ever seen.
_NET_SPREAD: dict[Segment, float] = {
    Segment.CASH: 0.18,
    Segment.INDEX_FUTURES: 0.22,
    Segment.INDEX_OPTIONS: 0.06,
    Segment.STOCK_FUTURES: 0.12,
    Segment.STOCK_OPTIONS: 0.10,
}

#: How much of the FII cash net the DIIs take the other side of. Domestic
#: institutions have absorbed most foreign selling for years; 0.8 with noise
#: reproduces that without making it a mirror image.
_DII_OFFSET = 0.8


class SimulatedInstitutionalFlowSource:
    """Implements the ``InstitutionalFlowSource`` port with generated data."""

    def __init__(self, clock: ReadableClock | None = None) -> None:
        self._clock = clock or SystemClock()

    @property
    def source(self) -> str:
        return "mock"

    async def read(
        self,
        tenant_id: TenantId,  # noqa: ARG002 — mirrors the port; the participant
        # file is an exchange-wide publication and is identical for every tenant.
        *,
        sessions: int,
        until: date | None = None,
    ) -> list[FlowDay]:
        # The exchange's trading date, not the server's. A process running in
        # UTC rolls over at 05:30 IST, which would hand the page "today" hours
        # before the session it names has opened.
        end = until or in_ist(self._clock.now()).date()
        return [self._day(session) for session in _sessions_back(end, sessions)]

    async def read_open_interest(
        self,
        tenant_id: TenantId,
        session: date,
    ) -> list[OiRow]:
        """This session's board, against the previous published session's.

        The previous day's nets are *regenerated from that day's own seed*
        rather than perturbed from today's. That is what makes the board
        consistent under navigation: stepping back a day and reading the Net
        OI column gives exactly the numbers the Change column was computed
        against.
        """
        previous, _ = await self.neighbours(tenant_id, session)
        today = _oi_board(session)
        yesterday = _oi_board(previous) if previous else today

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

    async def neighbours(
        self,
        tenant_id: TenantId,  # noqa: ARG002 — mirrors the port; see `read`.
        session: date,
    ) -> tuple[date | None, date | None]:
        latest = in_ist(self._clock.now()).date()
        previous = _step(session, -1)
        following = _step(session, 1)
        # Nothing is published for a session that has not happened yet, so the
        # forward arrow stops at the latest day rather than walking into a
        # future the archive cannot contain.
        return (previous, following if following <= latest else None)

    async def read_index(
        self,
        tenant_id: TenantId,  # noqa: ARG002 — mirrors the port; see `read`.
        session: date,  # noqa: ARG002
        index: str,  # noqa: ARG002
    ) -> None:
        """Always ``None``.

        A generated index close would be the one figure on the page a reader
        could check against their own screen, and it would be wrong. The page
        prints a dash instead, which is what a placeholder should look like.
        """
        return None

    def _day(self, session: date) -> FlowDay:
        # Seeded from the date alone, so the same session is the same numbers
        # in every process, for every tenant, forever. Tenant-specific flow
        # would be a nonsense: this is an exchange-wide publication.
        rng = Random(session.toordinal())  # noqa: S311 — a placeholder board, not a secret
        cash = _cash_segment(rng)
        return FlowDay(
            session_date=session,
            segments=(cash, *(_derivative_segment(rng, name) for name in _DERIVATIVES)),
        )


_DERIVATIVES: tuple[Segment, ...] = (
    Segment.INDEX_FUTURES,
    Segment.INDEX_OPTIONS,
    Segment.STOCK_FUTURES,
    Segment.STOCK_OPTIONS,
)


def _cash_segment(rng: Random) -> SegmentFlow:
    """Cash, the one segment with both participants."""
    fii_gross = _gross(rng, Segment.CASH)
    fii_net = fii_gross * rng.uniform(-_NET_SPREAD[Segment.CASH], _NET_SPREAD[Segment.CASH])

    dii_gross = _gross(rng, Segment.CASH) * rng.uniform(0.75, 1.15)
    # Mostly the other side of the FIIs, plus an independent component so the
    # two lines are correlated rather than reflected.
    dii_net = -fii_net * _DII_OFFSET + dii_gross * rng.uniform(-0.05, 0.05)

    return SegmentFlow(
        segment=Segment.CASH,
        fii=_split(fii_gross, fii_net),
        dii=_split(dii_gross, dii_net),
    )


def _derivative_segment(rng: Random, segment: Segment) -> SegmentFlow:
    """A derivative segment — FII line only, as the real file publishes it."""
    gross = _gross(rng, segment)
    spread = _NET_SPREAD[segment]
    return SegmentFlow(segment=segment, fii=_split(gross, gross * rng.uniform(-spread, spread)))


def _gross(rng: Random, segment: Segment) -> float:
    low, high = _TURNOVER[segment]
    return rng.uniform(low, high)


def _split(gross: float, net: float) -> ParticipantFlow:
    """Turn a turnover and a net into the buy and sell that produce them.

    ``buy + sell`` stays at ``gross`` and ``buy - sell`` lands on ``net``, so
    the published pair is internally consistent — a reader who subtracts the
    two columns gets the net column, which on real data they always can.
    """
    buy = (gross + net) / 2
    sell = (gross - net) / 2
    return ParticipantFlow(buy=_crore(buy), sell=_crore(sell))


def _crore(value: float) -> Decimal:
    """Two decimals, the way the exchange publishes crore figures."""
    return Decimal(f"{max(value, 0.0):.2f}")


# -- open interest ------------------------------------------------------------

#: Typical net position per participant per segment, in contracts. The scale
#: a participant's own book swings across; Client is not drawn at all (see
#: `_oi_board`).
_OI_SPREAD: dict[Segment, int] = {
    Segment.INDEX_FUTURES: 300_000,
    Segment.INDEX_OPTIONS: 900_000,
    Segment.STOCK_FUTURES: 4_000_000,
    Segment.STOCK_OPTIONS: 1_500_000,
}

#: Gross book size as a multiple of the net. A participant holding a 300k net
#: short is not holding 300k contracts — they hold far more on both sides, and
#: the expandable leg breakdown has to reflect that or it reads as though
#: everyone is one-directional.
_GROSS_MULTIPLE = 2.6

#: Participants whose books are generated directly. Client takes whatever is
#: left, because every long is somebody's short and the four nets must sum to
#: zero — see `open_interest.segment_imbalance`.
_DRAWN: tuple[Participant, ...] = (Participant.FII, Participant.PRO, Participant.DII)

#: How many sine components each participant's position is built from. Two is
#: enough to stop the series looking like a single clean wave and few enough
#: that the whole thing stays cheap to evaluate per request.
_HARMONICS = 3

#: Cycle lengths, in days. Long on purpose: **open interest is a stock, not a
#: flow.** Positions are carried across sessions and unwound gradually, so a
#: day-over-day change is a fraction of the level. An earlier version drew each
#: session independently and produced boards where a participant's book flipped
#: from +3.1m long to -2.5m short overnight — arithmetically fine, and nothing
#: a reader would ever see on a real exchange.
_PERIOD_DAYS = (200.0, 620.0)

#: Day-specific noise, as a fraction of the segment's spread. Small: it exists
#: so consecutive sessions are not perfectly smooth, not to move the level.
_JITTER = 0.004


def _oi_board(session: date) -> dict[tuple[Participant, Segment], FutureLegs | OptionLegs]:
    """One session's whole board, keyed by participant and segment.

    Deterministic in the date, like everything else here, and built so the
    four nets in each segment sum to exactly zero rather than approximately —
    an invariant a reader can check on screen.
    """
    board: dict[tuple[Participant, Segment], FutureLegs | OptionLegs] = {}

    for segment in OI_SEGMENTS:
        nets = {participant: _net_for(participant, segment, session) for participant in _DRAWN}
        nets[Participant.CLIENT] = -sum(nets.values())
        for participant, net in nets.items():
            board[(participant, segment)] = _legs(participant, segment, net)

    return board


def _net_for(participant: Participant, segment: Segment, session: date) -> int:
    """One participant's net position in one segment, as a slow wave in time.

    Seeded by the *series*, not by the day, so the shape of a participant's
    book is fixed once and the date only moves along it. That is what makes
    stepping back a session show a neighbouring position rather than an
    unrelated one — and it is why the Change column can be trusted.
    """
    shape = Random(f"oi:{participant.value}:{segment.value}")  # noqa: S311 — placeholder
    spread = _OI_SPREAD[segment]
    day = session.toordinal()

    level = 0.0
    for _ in range(_HARMONICS):
        amplitude = shape.uniform(0.15, 0.45) * spread
        period = shape.uniform(*_PERIOD_DAYS)
        phase = shape.uniform(0.0, 1.0)
        level += amplitude * sin(2 * pi * (day / period + phase))

    jitter = Random(f"oi:{participant.value}:{segment.value}:{day}")  # noqa: S311
    return int(level + jitter.uniform(-1.0, 1.0) * spread * _JITTER)


def _legs(participant: Participant, segment: Segment, net: int) -> FutureLegs | OptionLegs:
    """A book whose legs produce exactly ``net``.

    Built from the net outwards rather than the other way round: the zero-sum
    invariant lives on the nets, so they are the fixed quantity and the legs
    are arranged to agree with them.

    The split between the call and put leg is seeded by the series alone, so
    the breakdown behind a net drifts with it instead of being reshuffled
    every session.
    """
    shape = Random(f"legs:{participant.value}:{segment.value}")  # noqa: S311 — placeholder
    gross = int(abs(net) * _GROSS_MULTIPLE) + shape.randrange(1_000, 40_000)

    if segment in (Segment.INDEX_FUTURES, Segment.STOCK_FUTURES):
        # long - short == net, long + short == gross (give or take the parity
        # of the rounding, which lands on `long`).
        short = (gross - net) // 2
        return FutureLegs(long=short + net, short=short)

    # Options: net is (call_long + put_short) - (call_short + put_long), so the
    # bullish and bearish halves are split first and each half is then divided
    # between its call and put leg.
    bearish = gross - (gross + net) // 2
    # Derived from the bearish half rather than rounded independently, so the
    # two cannot drift apart: bullish - bearish is exactly `net`.
    bullish = bearish + net

    # No clamping: `gross` is at least 2.6x |net|, so both halves come out
    # positive and each leg is a fraction of its own half. A `max(_, 0)` here
    # would be dead code that, if it ever did fire, would silently break the
    # one property this function exists to guarantee — that the legs net to
    # `net`.
    call_long = int(bullish * shape.uniform(0.35, 0.65))
    call_short = int(bearish * shape.uniform(0.35, 0.65))
    return OptionLegs(
        call_long=call_long,
        call_short=call_short,
        put_long=bearish - call_short,
        put_short=bullish - call_long,
    )


def _step(session: date, direction: int) -> date:
    """The adjacent weekday. See `_sessions_back` on why holidays are not modelled."""
    cursor = session + timedelta(days=direction)
    while cursor.weekday() in _WEEKEND:
        cursor += timedelta(days=direction)
    return cursor


def _sessions_back(end: date, count: int) -> list[date]:
    """``count`` weekdays ending at or before ``end``, oldest first.

    Weekends only. Exchange holidays are not modelled: a generated series
    pretending to know that 2 October was closed would be claiming a calendar
    this placeholder does not have, and the real adapter will get the dates
    from the file itself rather than from any calendar we compute.
    """
    days: list[date] = []
    cursor = end
    while len(days) < count:
        if cursor.weekday() not in _WEEKEND:
            days.append(cursor)
        cursor -= timedelta(days=1)
    days.reverse()
    return days
