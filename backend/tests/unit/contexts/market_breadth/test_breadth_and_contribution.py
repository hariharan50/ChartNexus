"""Index breadth, index-point contributions and sector rotation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from marketcompass.contexts.market_breadth.domain.breadth import (
    UNCLASSIFIED,
    breadth_by_sector,
    count_breadth,
    weighted_change,
)
from marketcompass.contexts.market_breadth.domain.constituents import (
    Constituent,
    IndexSnapshot,
)
from marketcompass.contexts.market_breadth.domain.contribution import (
    contributions,
    normalised_weights,
    weight_slices,
)
from marketcompass.contexts.market_breadth.domain.rotation import (
    Quadrant,
    classify,
    positions,
)

pytestmark = pytest.mark.unit


def member(
    symbol: str,
    *,
    last: str,
    previous: str | None = "100",
    weight: str = "10",
    sector: str | None = "IT",
) -> Constituent:
    return Constituent(
        symbol=symbol,
        name=f"{symbol} Ltd",
        last=Decimal(last),
        previous_close=None if previous is None else Decimal(previous),
        weight_percent=Decimal(weight),
        sector=sector,
    )


# -- constituents -------------------------------------------------------------


def test_change_percent_is_none_without_a_baseline() -> None:
    """Not 0.00% — "no prior close" and "did not move" are different facts."""
    assert member("A", last="110", previous=None).change_percent is None
    assert member("A", last="110", previous="0").change_percent is None


def test_covered_weight_counts_only_priced_members() -> None:
    snapshot = IndexSnapshot(
        index="NIFTY50",
        level=Decimal(100),
        previous_close=Decimal(100),
        members=(
            member("A", last="110", weight="30"),
            member("B", last="110", previous=None, weight="70"),
        ),
        universe=2,
    )

    assert snapshot.covered_weight_percent == Decimal(30)
    assert len(snapshot.priced) == 1


# -- breadth ------------------------------------------------------------------


def test_a_move_inside_the_deadband_is_unchanged_not_a_direction() -> None:
    counts = count_breadth(
        [
            member("UP", last="101"),
            member("DOWN", last="99"),
            member("FLAT", last="100.02"),
        ]
    )

    assert (counts.advancing, counts.declining, counts.unchanged) == (1, 1, 1)


def test_unpriced_members_are_counted_apart_from_unchanged() -> None:
    counts = count_breadth([member("A", last="100", previous=None), member("B", last="101")])

    assert counts.unpriced == 1
    assert counts.unchanged == 0
    # `counted` is what produced a reading, so the ratio has an honest base.
    assert counts.counted == 1


def test_ratio_is_none_when_nothing_declined() -> None:
    counts = count_breadth([member("A", last="105"), member("B", last="103")])

    assert counts.ratio is None
    assert counts.advancing_percent == Decimal(100)
    assert counts.net == 2


def test_weighted_change_lets_the_heavy_name_dominate() -> None:
    heavy = member("HEAVY", last="110", weight="90")
    light = member("LIGHT", last="90", weight="10")

    assert weighted_change([heavy, light]) == Decimal(8)


def test_weighted_change_is_none_when_nothing_is_priced() -> None:
    assert weighted_change([member("A", last="100", previous=None)]) is None


def test_unsectored_members_are_grouped_not_dropped() -> None:
    sectors = breadth_by_sector(
        [member("A", last="110", sector=None), member("B", last="110", sector="IT")]
    )

    assert {entry.sector for entry in sectors} == {UNCLASSIFIED, "IT"}


def test_sectors_are_heaviest_first() -> None:
    sectors = breadth_by_sector(
        [
            member("SMALL", last="110", weight="5", sector="PHARMA"),
            member("BIG", last="110", weight="40", sector="BANKING"),
        ]
    )

    assert [entry.sector for entry in sectors] == ["BANKING", "PHARMA"]


# -- contribution -------------------------------------------------------------


def test_weights_are_renormalised_over_what_was_priced() -> None:
    weights = normalised_weights(
        [member("A", last="1", weight="30"), member("B", last="1", weight="10")]
    )

    assert weights == {"A": Decimal(75), "B": Decimal(25)}


def test_normalised_weights_of_a_weightless_group_is_empty() -> None:
    assert normalised_weights([member("A", last="1", weight="0")]) == {}


def test_contributions_sum_to_the_index_move_on_a_fully_priced_index() -> None:
    """The bars must add up to the number in the page header."""
    snapshot = IndexSnapshot(
        index="TEST",
        level=Decimal(10100),
        previous_close=Decimal(10000),
        members=(
            member("UP", last="110", weight="50"),
            member("DOWN", last="98", weight="50"),
        ),
        universe=2,
    )

    board = contributions(snapshot)

    # 50% x +10% x 10000 = +500; 50% x -2% x 10000 = -100.
    assert board.modelled_points == Decimal(400)
    assert board.actual_points == Decimal(100)
    # The residual is published, not hidden.
    assert board.gap == Decimal(-300)


def test_gainers_and_losers_are_ranked_by_push() -> None:
    snapshot = IndexSnapshot(
        index="TEST",
        level=Decimal(10000),
        previous_close=Decimal(10000),
        members=(
            member("SMALLUP", last="101", weight="10"),
            member("BIGUP", last="105", weight="60"),
            member("DOWN", last="95", weight="30"),
        ),
        universe=3,
    )

    board = contributions(snapshot)

    assert [row.symbol for row in board.gainers] == ["BIGUP", "SMALLUP"]
    assert [row.symbol for row in board.losers] == ["DOWN"]


def test_no_index_baseline_yields_no_contributions_rather_than_a_guess() -> None:
    snapshot = IndexSnapshot(
        index="TEST",
        level=None,
        previous_close=None,
        members=(member("A", last="110"),),
        universe=1,
    )

    board = contributions(snapshot)

    assert board.contributions == ()
    assert board.actual_points is None


def test_weight_slices_are_heaviest_first_and_share_sums_to_a_hundred() -> None:
    rows = weight_slices(
        [member("A", last="110", weight="30"), member("B", last="110", weight="10")]
    )

    assert [row.label for row in rows] == ["A", "B"]
    assert sum(row.share_percent for row in rows) == Decimal(100)


# -- rotation -----------------------------------------------------------------


def test_quadrants_split_on_strength_and_participation() -> None:
    assert classify(Decimal(1), Decimal(70)) is Quadrant.LEADING
    assert classify(Decimal(-1), Decimal(70)) is Quadrant.IMPROVING
    assert classify(Decimal(1), Decimal(30)) is Quadrant.WEAKENING
    assert classify(Decimal(-1), Decimal(30)) is Quadrant.LAGGING


def test_strength_inside_the_deadband_is_not_a_direction() -> None:
    assert classify(Decimal("0.01"), Decimal(70)) is Quadrant.IMPROVING


def test_exactly_half_the_sector_advancing_is_not_broad() -> None:
    assert classify(Decimal(1), Decimal(50)) is Quadrant.WEAKENING


def test_positions_measure_strength_against_the_index() -> None:
    sectors = breadth_by_sector(
        [
            member("A", last="103", weight="20", sector="IT"),
            member("B", last="97", weight="20", sector="PHARMA"),
        ]
    )

    placed = positions(sectors, Decimal(1))
    by_sector = {entry.sector: entry for entry in placed}

    assert by_sector["IT"].relative_strength == Decimal(2)
    assert by_sector["PHARMA"].relative_strength == Decimal(-4)
    assert by_sector["IT"].participation_offset == Decimal(50)


def test_positions_fall_back_to_a_zero_baseline_without_an_index_move() -> None:
    sectors = breadth_by_sector([member("A", last="103", sector="IT")])

    placed = positions(sectors, None)

    assert placed[0].relative_strength == Decimal(3)


def test_movers_name_the_sector_s_own_leaders_and_laggards() -> None:
    sectors = breadth_by_sector(
        [
            member("BEST", last="120", sector="IT"),
            member("OK", last="105", sector="IT"),
            member("WORST", last="80", sector="IT"),
        ]
    )

    placed = positions(sectors, Decimal(0))

    assert placed[0].leaders == ("BEST", "OK")
    assert placed[0].laggards == ("WORST",)
