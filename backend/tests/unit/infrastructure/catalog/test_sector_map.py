"""The one hand-maintained table in the catalog.

Everything else is derived from the exchange's own symbol master and corrects
itself daily. This file cannot, so these tests are the only thing standing
between a careless edit and a silently wrong sector filter.
"""

from __future__ import annotations

import pytest

from chartnexus.infrastructure.catalog.sector_map import (
    INDEX_MEMBERS,
    SECTORS,
    indices_for,
    sector_for,
)

pytestmark = pytest.mark.unit

#: The F&O stock universe as of the 2026-09-18 symbol master.
EXPECTED_STOCKS = 210


def test_the_map_covers_the_whole_stock_universe() -> None:
    """A stock missing here loses its sector, its filter entry and its row in
    the sector panel — silently."""
    assert len(SECTORS) == EXPECTED_STOCKS


def test_every_symbol_is_upper_case_and_trimmed() -> None:
    """Lookups normalise, but a stray key would never be hit."""
    assert all(symbol == symbol.strip().upper() for symbol in SECTORS)


def test_no_sector_is_blank() -> None:
    assert all(sector and sector.strip() for sector in SECTORS.values())


def test_the_sector_vocabulary_stays_small_enough_to_be_a_filter() -> None:
    """A dropdown with forty options is not a filter. If this trips, the right
    fix is usually to merge two near-identical sectors, not to raise the cap."""
    assert len(set(SECTORS.values())) <= 30


def test_nifty50_holds_exactly_fifty_names() -> None:
    """The obvious way an edit here goes wrong, and invisible by eye."""
    assert len(INDEX_MEMBERS["NIFTY50"]) == 50


def test_banknifty_holds_exactly_twelve_names() -> None:
    assert len(INDEX_MEMBERS["BANKNIFTY"]) == 12


def test_every_index_member_is_a_classified_stock() -> None:
    """An index member absent from the sector table is a typo, not a stock."""
    for name, members in INDEX_MEMBERS.items():
        unknown = sorted(members - set(SECTORS))
        assert unknown == [], f"{name} lists symbols with no sector: {unknown}"


def test_every_bank_nifty_member_is_classified_as_banking() -> None:
    assert {SECTORS[symbol] for symbol in INDEX_MEMBERS["BANKNIFTY"]} == {"BANKING"}


# -- lookups ----------------------------------------------------------------


@pytest.mark.parametrize("raw", ["RELIANCE", " reliance ", "Reliance"])
def test_lookup_normalises(raw: str) -> None:
    assert sector_for(raw) == "OIL & GAS"


def test_an_unclassified_symbol_has_no_sector_rather_than_a_placeholder() -> None:
    """Index contracts and newly-added stocks both land here. `None` is a
    normal answer that every consumer already tolerates."""
    assert sector_for("NIFTY") is None
    assert sector_for("SOMETHINGNEW") is None


def test_ampersand_symbols_resolve() -> None:
    assert sector_for("M&M") == "AUTO"
    assert sector_for("GVT&D") == "CAPITAL GOODS"


def test_index_membership_is_sorted_and_may_be_multiple() -> None:
    assert indices_for("HDFCBANK") == ("BANKNIFTY", "NIFTY50")
    assert indices_for("SBIN") == ("BANKNIFTY", "NIFTY50")


def test_a_stock_in_no_tracked_index_returns_empty() -> None:
    assert indices_for("360ONE") == ()
