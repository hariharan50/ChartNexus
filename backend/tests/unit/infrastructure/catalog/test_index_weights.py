"""The second hand-maintained table in the catalog.

Index weights cannot correct themselves, and a wrong one is invisible by eye:
the Contributors bars still point the right way, they are just the wrong
length. These tests catch the errors a careless edit actually makes — a symbol
that drifted out of the membership list, a weight that lost its decimal point,
a whole index that no longer adds up.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from marketcompass.infrastructure.catalog.index_weights import (
    INDEX_INSTRUMENTS,
    INDEX_WEIGHTS,
    TRACKED_INDICES,
    label_for,
    weight_of,
    weights_for,
)
from marketcompass.infrastructure.catalog.sector_map import INDEX_MEMBERS, SECTORS

pytestmark = pytest.mark.unit

#: How far the published weights may sum from 100 before the table is wrong
#: rather than merely rounded. One decimal per member across fifty members
#: leaves a couple of points of legitimate slack; ten would be a lost row.
_SUM_TOLERANCE = Decimal(3)


def test_every_tracked_index_has_a_weight_table() -> None:
    assert set(TRACKED_INDICES) == set(INDEX_WEIGHTS)


def test_weighted_symbols_are_all_index_members() -> None:
    """A weight for a name the index no longer holds is dead arithmetic."""
    for index, weights in INDEX_WEIGHTS.items():
        members = INDEX_MEMBERS[index]
        assert set(weights) <= set(members), f"{index} weights a non-member"


def test_every_member_carries_a_weight() -> None:
    """A member with no weight contributes nothing and drops out of the donut."""
    for index, weights in INDEX_WEIGHTS.items():
        missing = sorted(INDEX_MEMBERS[index] - set(weights))
        assert not missing, f"{index} members without a weight: {missing}"


def test_each_index_sums_to_about_a_hundred() -> None:
    for index, weights in INDEX_WEIGHTS.items():
        total = sum(weights.values(), Decimal(0))
        assert abs(total - Decimal(100)) <= _SUM_TOLERANCE, f"{index} sums to {total}"


def test_no_weight_is_zero_or_negative() -> None:
    for index, weights in INDEX_WEIGHTS.items():
        for symbol, weight in weights.items():
            assert weight > 0, f"{index}/{symbol} carries {weight}"


def test_no_single_name_dominates_more_than_the_index_rules_allow() -> None:
    """NSE caps a single stock at 33% of a sectoral index and 10% is the
    practical ceiling in NIFTY 50 — a 100.0 here is a lost decimal point."""
    for index, weights in INDEX_WEIGHTS.items():
        heaviest = max(weights.values())
        assert heaviest <= Decimal(35), f"{index} has a {heaviest}% member"


def test_every_weighted_stock_also_has_a_sector() -> None:
    """Sector Rotation groups by the sector map; an unmapped heavyweight would
    quietly land the whole of its weight in UNCLASSIFIED."""
    for index, weights in INDEX_WEIGHTS.items():
        unmapped = sorted(symbol for symbol in weights if symbol not in SECTORS)
        assert not unmapped, f"{index} weights unsectored names: {unmapped}"


def test_each_index_names_the_instrument_its_level_is_read_from() -> None:
    assert set(TRACKED_INDICES) <= set(INDEX_INSTRUMENTS)


def test_lookups_normalise_their_input() -> None:
    assert weights_for("nifty50") == weights_for("NIFTY50")
    assert weight_of("nifty50", " reliance ") == weight_of("NIFTY50", "RELIANCE")


def test_an_unweighted_symbol_reads_as_zero_not_as_an_error() -> None:
    """It still belongs to the index and still appears in the counts."""
    assert weight_of("NIFTY50", "NOTAMEMBER") == Decimal(0)
    assert weights_for("NOTANINDEX") == {}


def test_labels_fall_back_to_the_key() -> None:
    assert label_for("NIFTY50") == "NIFTY 50"
    assert label_for("MADEUP") == "MADEUP"
