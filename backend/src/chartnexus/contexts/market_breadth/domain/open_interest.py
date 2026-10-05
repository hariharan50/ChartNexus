"""Participant-wise open interest in the derivative segments.

The other half of the daily participant file, and a different measurement from
the cash flow in :mod:`flows`: that one is **value traded** in rupees crore,
this one is **positions held**, counted in contracts. They are published
together and read together, and confusing them is the obvious mistake — a
participant can be a net buyer on the day and still hold a net short book.

**The four nets sum to zero in every segment**, and that is not a modelling
choice: every long contract is somebody's short. ``segment_imbalance`` exists
so the invariant can be checked rather than assumed, because a board that
violates it is a board with a participant missing or a sign flipped.

**Net is a directional read, not an arithmetic total.** For futures it is
simply long minus short. For options it is bullish legs minus bearish ones —
a long call and a short put both profit from a rise — which is what makes an
options net comparable to a futures net instead of being a meaningless sum of
premiums. ``OptionLegs.net`` writes that formula down once.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from chartnexus.contexts.market_breadth.domain.flows import Participant, Segment

#: The segments that carry open interest. Cash is deliberately absent: shares
#: bought in the cash market are not a position with an expiry, and the
#: published file does not report one for them.
OI_SEGMENTS: tuple[Segment, ...] = (
    Segment.INDEX_FUTURES,
    Segment.INDEX_OPTIONS,
    Segment.STOCK_FUTURES,
    Segment.STOCK_OPTIONS,
)

#: Participant order on the board. FII first because it is the one most
#: readers came to look at; Client last because it is the residual side.
PARTICIPANT_ORDER: tuple[Participant, ...] = (
    Participant.FII,
    Participant.PRO,
    Participant.CLIENT,
    Participant.DII,
)


@dataclass(frozen=True, slots=True)
class OptionLegs:
    """The four option positions the file reports, in contracts."""

    call_long: int
    call_short: int
    put_long: int
    put_short: int

    @property
    def net(self) -> int:
        """Bullish legs minus bearish ones.

        A long call and a short put both gain when the underlying rises; a
        short call and a long put both gain when it falls. Netting them that
        way makes this number mean the same thing as a futures net — "how this
        participant is positioned" — which is the only reason the two sit in
        one column.
        """
        return (self.call_long + self.put_short) - (self.call_short + self.put_long)

    @property
    def total(self) -> int:
        """Every contract held, regardless of side — the size of the book."""
        return self.call_long + self.call_short + self.put_long + self.put_short


@dataclass(frozen=True, slots=True)
class FutureLegs:
    """A futures book's two sides, in contracts."""

    long: int
    short: int

    @property
    def net(self) -> int:
        return self.long - self.short

    @property
    def total(self) -> int:
        return self.long + self.short


@dataclass(frozen=True, slots=True)
class OiRow:
    """One participant's position in one segment, against yesterday's.

    ``previous_net`` is the same participant's net on the previous published
    session, carried on the row rather than fetched separately so the change
    column cannot disagree with the net beside it.
    """

    participant: Participant
    segment: Segment
    net: int
    previous_net: int
    #: The legs behind ``net``. ``OptionLegs`` in the two options segments,
    #: ``FutureLegs`` in the futures ones, ``None`` when the source published
    #: a net without a breakdown.
    legs: OptionLegs | FutureLegs | None = None

    @property
    def change(self) -> int:
        """Contracts added or removed since the previous session."""
        return self.net - self.previous_net

    @property
    def is_options(self) -> bool:
        return isinstance(self.legs, OptionLegs)


@dataclass(frozen=True, slots=True)
class OiGroup:
    """One band of the board — a participant, or a segment."""

    #: The enum value the band is keyed by, for the client to label it.
    key: str
    rows: tuple[OiRow, ...]

    @property
    def net(self) -> int:
        """The band's combined net. Meaningful down a participant, not across
        a segment — see ``segment_imbalance``, which is the same sum and is
        expected to be zero."""
        return sum(row.net for row in self.rows)

    @property
    def change(self) -> int:
        return sum(row.change for row in self.rows)


def by_participant(rows: Sequence[OiRow]) -> list[OiGroup]:
    """Grouped participant-first: FII's four segments, then Pro's, and so on."""
    return [
        OiGroup(
            key=participant.value,
            rows=tuple(
                row
                for segment in OI_SEGMENTS
                for row in rows
                if row.participant is participant and row.segment is segment
            ),
        )
        for participant in PARTICIPANT_ORDER
        if any(row.participant is participant for row in rows)
    ]


def by_segment(rows: Sequence[OiRow]) -> list[OiGroup]:
    """Grouped segment-first: every participant's index futures, then options.

    The other half of the page's view toggle. Same rows, same order within a
    band — only the nesting changes, so a number never moves between views.
    """
    return [
        OiGroup(
            key=segment.value,
            rows=tuple(
                row
                for participant in PARTICIPANT_ORDER
                for row in rows
                if row.segment is segment and row.participant is participant
            ),
        )
        for segment in OI_SEGMENTS
        if any(row.segment is segment for row in rows)
    ]


def segment_imbalance(rows: Sequence[OiRow]) -> dict[str, int]:
    """How far each segment's four nets are from summing to zero.

    Zero everywhere on a complete board. Published rather than asserted: a
    real file occasionally rounds, and a non-zero here is a fact about the
    data that the page can surface instead of an exception that hides it.
    """
    totals: dict[str, int] = {}
    for row in rows:
        totals[row.segment.value] = totals.get(row.segment.value, 0) + row.net
    return totals
