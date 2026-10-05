"""Institutional cash and derivative flow, as pure arithmetic.

FII and DII activity is published as gross buy and gross sell per segment per
session, in rupees crore. Everything the Analysis pages show about it — the
net, the rolling total, the run of consecutive same-side days, the cumulative
line — is derived here so no caller re-invents a sign convention.

**Net is buy minus sell, always.** Positive means the participant put money
in. That is the only convention in this module, and it is applied identically
to FIIs and DIIs so that "FII sold what DII bought" can be read off two numbers
of opposite sign rather than two numbers with different meanings.

**Crores, not rupees.** The published figures are in crore and are shown in
crore; converting them to rupees here would buy nothing and would turn every
readable four-digit number into an eleven-digit one. The unit is part of the
type's meaning — see ``Crore``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

#: Rupees crore. An alias rather than a wrapper type: it costs nothing, and it
#: makes every signature below say which unit it is in.
Crore = Decimal

ZERO = Decimal("0")


class Segment(StrEnum):
    """The segments the daily participant file splits activity into.

    Cash is the one that moves the index; the four derivative segments are
    what the Summary page adds beside it. They are not interchangeable — a
    crore of index options premium is not a crore of equity bought — so they
    are never summed into a single "FII net" anywhere in this module.
    """

    CASH = "cash"
    INDEX_FUTURES = "index_futures"
    INDEX_OPTIONS = "index_options"
    STOCK_FUTURES = "stock_futures"
    STOCK_OPTIONS = "stock_options"


class Participant(StrEnum):
    """Who the exchange attributes a position to.

    Four categories, not two. The value tables published for the cash market
    name only FIIs and DIIs, but the participant-wise **open interest** file
    splits the derivative book four ways — and it has to, because the four nets
    sum to zero in every segment. Leaving ``PRO`` and ``CLIENT`` out would show
    an FII short with nobody on the other side of it.
    """

    FII = "fii"
    DII = "dii"
    #: Proprietary desks — the brokers trading their own book.
    PRO = "pro"
    #: Everybody else, retail included. In practice the residual side.
    CLIENT = "client"


@dataclass(frozen=True, slots=True)
class ParticipantFlow:
    """One participant's gross activity in one segment on one day."""

    buy: Crore
    sell: Crore

    @property
    def net(self) -> Crore:
        return self.buy - self.sell

    @property
    def turnover(self) -> Crore:
        """Both sides added — how *busy* the participant was, not which way.

        A ₹50 crore net on ₹200 crore of turnover and the same net on ₹12,000
        crore are different events, and the Summary page shows both.
        """
        return self.buy + self.sell


@dataclass(frozen=True, slots=True)
class SegmentFlow:
    """Both participants in one segment on one day.

    ``dii`` is optional because the published derivative breakdown carries no
    DII line: domestic institutions' F&O activity is reported inside the
    broader "DII" cash figure and not split by contract type. ``None`` is the
    honest answer there, and every consumer renders it as a dash.
    """

    segment: Segment
    fii: ParticipantFlow
    dii: ParticipantFlow | None = None

    def flow_for(self, participant: Participant) -> ParticipantFlow | None:
        return self.fii if participant is Participant.FII else self.dii


@dataclass(frozen=True, slots=True)
class FlowDay:
    """One session's published participant activity, across every segment.

    Value traded, in rupees crore. Positions *held* are a separate
    measurement, published in a separate file and modelled in
    :mod:`open_interest` — a participant can be a net buyer on the day and
    still hold a net short book, and merging the two here would invite exactly
    that confusion.
    """

    session_date: date
    segments: tuple[SegmentFlow, ...] = ()

    def segment(self, wanted: Segment) -> SegmentFlow | None:
        for entry in self.segments:
            if entry.segment is wanted:
                return entry
        return None


@dataclass(frozen=True, slots=True)
class CashDay:
    """One session reduced to the two cash nets and their running total.

    The shape the Cash Market chart plots: a pair of bars and two cumulative
    lines per session. ``fii_cumulative`` restarts at the first day of the
    requested window rather than at any absolute epoch — the line answers "over
    the period on screen", which is the only question a windowed chart can
    honestly answer.
    """

    session_date: date
    fii_buy: Crore
    fii_sell: Crore
    dii_buy: Crore
    dii_sell: Crore
    fii_net: Crore
    dii_net: Crore
    fii_cumulative: Crore
    dii_cumulative: Crore


def cash_history(days: Sequence[FlowDay]) -> list[CashDay]:
    """The cash segment of each session, oldest first, with running totals.

    Days carrying no cash segment are dropped rather than zero-filled: a
    session with nothing published is not a session in which nobody traded.
    """
    ordered = sorted(days, key=lambda day: day.session_date)
    running_fii = ZERO
    running_dii = ZERO
    out: list[CashDay] = []

    for day in ordered:
        cash = day.segment(Segment.CASH)
        if cash is None:
            continue
        dii = cash.dii or ParticipantFlow(ZERO, ZERO)
        running_fii += cash.fii.net
        running_dii += dii.net
        out.append(
            CashDay(
                session_date=day.session_date,
                fii_buy=cash.fii.buy,
                fii_sell=cash.fii.sell,
                dii_buy=dii.buy,
                dii_sell=dii.sell,
                fii_net=cash.fii.net,
                dii_net=dii.net,
                fii_cumulative=running_fii,
                dii_cumulative=running_dii,
            )
        )
    return out


def net_streak(values: Sequence[Crore]) -> int:
    """How many sessions in a row ended on the same side, signed.

    ``+4`` is four consecutive net-buying days, ``-2`` two consecutive selling
    days, ``0`` a flat latest session. Counted backwards from the **last**
    element, so the sequence must be oldest-first like everything else here.

    An exact zero breaks a run rather than extending it: a day with no net is
    not a day of buying, and treating it as one would report a streak that did
    not happen.
    """
    if not values:
        return 0
    last = values[-1]
    if last == ZERO:
        return 0
    sign = 1 if last > ZERO else -1
    count = 0
    for value in reversed(values):
        if value == ZERO or (value > ZERO) != (sign > 0):
            break
        count += 1
    return count * sign


def window_total(values: Sequence[Crore], sessions: int) -> Crore:
    """The net over the last ``sessions`` entries, or over all of them.

    Shorter history than the window asked for is normal at the start of a
    series; it returns what exists rather than padding with zeros, and the
    caller states how many sessions it actually covered.
    """
    if sessions <= 0 or not values:
        return ZERO
    return sum(values[-sessions:], ZERO)
