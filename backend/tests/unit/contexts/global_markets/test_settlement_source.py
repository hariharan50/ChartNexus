"""NSE IX's end-of-day settlement files, against real captured responses.

Both fixtures are unmodified responses from 28-Sep-2026, the morning the GIA
card was reported wrong. They are what pins the fix: the live board had the
front-month contract closing at 23,236.00, and the exchange's own bhavcopy -
below, verbatim - settles it at 23,188.50.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from chartnexus.infrastructure.global_markets.nseix.settlement_source import (
    bhavcopy_url,
    contract_key,
    parse_bhavcopy,
)

pytestmark = pytest.mark.unit

HERE = Path(__file__).parent
BHAVCOPY = HERE / "nseix_futures_bhavcopy.csv"
LISTING = HERE / "nseix_daily_reports.json"


@pytest.fixture
def bhavcopy() -> str:
    return BHAVCOPY.read_text(encoding="utf-8")


class TestBhavcopyUrl:
    def test_the_listing_names_the_current_futures_bhavcopy(self) -> None:
        """Asked, never guessed. The filename is ``DDMMYY`` and reconstructing
        it from today's date would need NSE IX's holiday calendar to walk back
        to the last published session."""
        url = bhavcopy_url(json.loads(LISTING.read_text(encoding="utf-8")))

        assert url is not None
        assert url.endswith("G_T_Bhavcopy_FO_250926.CSV")

    def test_the_file_is_found_by_key_not_by_position(self) -> None:
        """The listing nests by day and then by session, and that shape is the
        exchange's to change without notice."""
        buried = {"anything": [{"else": [{"FILEKEY": "G_T_Bhavcopy_FO_", "fileurl": "u"}]}]}

        assert bhavcopy_url(buried) == "u"

    def test_a_listing_without_one_yields_nothing_rather_than_raising(self) -> None:
        assert bhavcopy_url({"data": [{"Current Day": []}]}) is None
        assert bhavcopy_url([]) is None
        assert bhavcopy_url(None) is None


class TestParseBhavcopy:
    def test_the_front_month_settles_where_the_exchange_says_it_does(self, bhavcopy: str) -> None:
        """23,188.50 - the number the reported-wrong card should have shown,
        and the one every reference board quotes the contract against."""
        table = parse_bhavcopy(bhavcopy)

        assert table[contract_key("NIFTY", "29-Sep-2026")] == Decimal("23188.5")

    def test_the_board_s_own_expiry_spelling_looks_the_contract_up(self, bhavcopy: str) -> None:
        """The live board spells the month ``29-Sep-2026`` and the bhavcopy
        spells it ``29-SEP-2026``. A lookup that did not fold them would miss
        every contract and silently fall back."""
        table = parse_bhavcopy(bhavcopy)

        assert contract_key("NIFTY", "29-Sep-2026") in table
        assert contract_key("nifty", " 29-sep-2026 ") in table

    def test_symbols_sharing_a_prefix_do_not_collide(self, bhavcopy: str) -> None:
        """``NIFTY``, ``NIFTYIT``, ``NIFTYFPI`` and ``NIFTYNXT50`` all begin
        the same way, so the contract string is split from the right. Matching
        left-to-right would quote NIFTYIT's 28,173 as NIFTY's settlement."""
        table = parse_bhavcopy(bhavcopy)

        assert table[contract_key("NIFTY", "29-Sep-2026")] == Decimal("23188.5")
        assert table[contract_key("NIFTYIT", "29-Sep-2026")] == Decimal("28173")
        assert table[contract_key("NIFTYNXT50", "29-Sep-2026")] == Decimal("71809.5")
        assert table[contract_key("NIFTYFPI", "29-Sep-2026")] == Decimal("1505.7")

    def test_contracts_that_did_not_trade_still_carry_a_settlement(self, bhavcopy: str) -> None:
        """Their ``CLOSE_PRIC`` is blank and only ``SETTLEMENT`` is filled, so
        preferring the close would leave the far months empty for no gain."""
        table = parse_bhavcopy(bhavcopy)

        assert table[contract_key("NIFTY", "29-Jun-2027")] == Decimal("23797.5")

    def test_the_header_row_is_not_mistaken_for_a_contract(self, bhavcopy: str) -> None:
        assert not any(key.startswith("CONTRACT") for key in parse_bhavcopy(bhavcopy))

    def test_every_key_is_symbol_pipe_expiry(self, bhavcopy: str) -> None:
        table = parse_bhavcopy(bhavcopy)

        assert table
        for key in table:
            symbol, _, expiry = key.partition("|")
            assert symbol and expiry.count("-") == 2

    @pytest.mark.parametrize(
        "body",
        [
            "",
            "CONTRACT_D,PREVIOUS_S\n",
            "FUTIDXNIFTY29-SEP-2026,1,2,3,4,5\n",  # truncated before SETTLEMENT
            "FUTSTKRELIANCE29-SEP-2026,1,2,3,4,,0,0,0,0,0,0\n",  # settles at zero
        ],
    )
    def test_unusable_input_yields_an_empty_table_rather_than_raising(self, body: str) -> None:
        assert parse_bhavcopy(body) == {}
