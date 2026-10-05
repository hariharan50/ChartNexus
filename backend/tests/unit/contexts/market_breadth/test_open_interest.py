"""Participant-wise open interest — the net formula and the two groupings."""

from __future__ import annotations

import pytest

from chartnexus.contexts.market_breadth.domain.flows import Participant, Segment
from chartnexus.contexts.market_breadth.domain.open_interest import (
    OI_SEGMENTS,
    PARTICIPANT_ORDER,
    FutureLegs,
    OiRow,
    OptionLegs,
    by_participant,
    by_segment,
    segment_imbalance,
)

pytestmark = pytest.mark.unit


def row(
    participant: Participant,
    segment: Segment,
    *,
    net: int = 100,
    previous: int = 80,
) -> OiRow:
    return OiRow(participant=participant, segment=segment, net=net, previous_net=previous)


def board() -> list[OiRow]:
    """Every participant in every segment — a complete board."""
    return [
        row(participant, segment) for participant in PARTICIPANT_ORDER for segment in OI_SEGMENTS
    ]


# -- the net formula ----------------------------------------------------------


def test_futures_net_is_long_minus_short() -> None:
    assert FutureLegs(long=900, short=400).net == 500
    assert FutureLegs(long=400, short=900).net == -500


def test_options_net_is_bullish_legs_minus_bearish_ones() -> None:
    """A long call and a short put both gain when the underlying rises."""
    legs = OptionLegs(call_long=500, call_short=100, put_long=50, put_short=200)

    assert legs.net == (500 + 200) - (100 + 50)


def test_total_counts_every_contract_regardless_of_side() -> None:
    assert OptionLegs(call_long=1, call_short=2, put_long=3, put_short=4).total == 10
    assert FutureLegs(long=7, short=3).total == 10


def test_change_is_measured_against_the_previous_session() -> None:
    assert row(Participant.FII, Segment.INDEX_FUTURES, net=120, previous=100).change == 20
    assert row(Participant.FII, Segment.INDEX_FUTURES, net=80, previous=100).change == -20


def test_a_row_knows_whether_it_carries_option_legs() -> None:
    futures = OiRow(
        participant=Participant.FII,
        segment=Segment.STOCK_FUTURES,
        net=1,
        previous_net=1,
        legs=FutureLegs(long=2, short=1),
    )
    options = OiRow(
        participant=Participant.FII,
        segment=Segment.STOCK_OPTIONS,
        net=1,
        previous_net=1,
        legs=OptionLegs(call_long=2, call_short=1, put_long=0, put_short=0),
    )

    assert not futures.is_options
    assert options.is_options


# -- groupings ----------------------------------------------------------------


def test_participant_grouping_keeps_the_display_order() -> None:
    groups = by_participant(board())

    assert [group.key for group in groups] == [p.value for p in PARTICIPANT_ORDER]
    assert [r.segment for r in groups[0].rows] == list(OI_SEGMENTS)


def test_segment_grouping_keeps_the_display_order() -> None:
    groups = by_segment(board())

    assert [group.key for group in groups] == [s.value for s in OI_SEGMENTS]
    assert [r.participant for r in groups[0].rows] == list(PARTICIPANT_ORDER)


def test_the_two_groupings_hold_exactly_the_same_rows() -> None:
    """The page's view toggle must not make a number appear or vanish."""
    rows = board()

    flat_a = sorted((r.participant, r.segment, r.net) for g in by_participant(rows) for r in g.rows)
    flat_b = sorted((r.participant, r.segment, r.net) for g in by_segment(rows) for r in g.rows)

    assert flat_a == flat_b == sorted((r.participant, r.segment, r.net) for r in rows)


def test_a_band_with_no_rows_is_not_emitted() -> None:
    """A board missing a participant shows three bands, not four empty ones."""
    rows = [r for r in board() if r.participant is not Participant.DII]

    assert Participant.DII.value not in {group.key for group in by_participant(rows)}


def test_a_band_sums_its_own_rows() -> None:
    rows = [
        row(Participant.FII, Segment.INDEX_FUTURES, net=100, previous=40),
        row(Participant.FII, Segment.INDEX_OPTIONS, net=-30, previous=-10),
    ]

    group = by_participant(rows)[0]

    assert group.net == 70
    assert group.change == (100 - 40) + (-30 - -10)


# -- the zero-sum invariant ---------------------------------------------------


def test_imbalance_is_zero_when_every_long_has_its_short() -> None:
    rows = [
        row(Participant.FII, Segment.INDEX_FUTURES, net=300),
        row(Participant.PRO, Segment.INDEX_FUTURES, net=-100),
        row(Participant.DII, Segment.INDEX_FUTURES, net=-50),
        row(Participant.CLIENT, Segment.INDEX_FUTURES, net=-150),
    ]

    assert segment_imbalance(rows) == {Segment.INDEX_FUTURES.value: 0}


def test_imbalance_reports_a_residual_rather_than_hiding_it() -> None:
    """A non-zero means the board is incomplete — a fact, not an exception."""
    rows = [
        row(Participant.FII, Segment.INDEX_FUTURES, net=300),
        row(Participant.PRO, Segment.INDEX_FUTURES, net=-100),
    ]

    assert segment_imbalance(rows) == {Segment.INDEX_FUTURES.value: 200}
