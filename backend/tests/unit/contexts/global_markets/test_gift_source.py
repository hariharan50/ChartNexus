"""The NSE IX market-watch parser, against a real captured payload.

``nseix_market_watch.json`` is an actual response, saved unmodified. It carries
two contracts - 29-Sep and 27-Oct - which is exactly the case the front-month
pick exists to get right.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from marketcompass.contexts.global_markets.domain.markets import GIFT_KEY
from marketcompass.contexts.global_markets.domain.quotes import DataSource
from marketcompass.infrastructure.global_markets.nseix.gift_source import (
    front_month,
    to_quote,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 24, 3, 30, tzinfo=UTC)
FIXTURE = Path(__file__).parent / "nseix_market_watch.json"


@pytest.fixture
def payload() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestFrontMonth:
    def test_the_nearest_expiry_wins(self, payload: dict[str, Any]) -> None:
        """Quoting October as "GIFT NIFTY" would put the implied open out by
        the whole calendar spread - 55 points on this very board."""
        row = front_month(payload)

        assert row is not None
        assert row["EXPIRYDATE"] == "29-Sep-2026"
        assert row["LASTPRICE"] == "23267.50"

    def test_the_pick_does_not_depend_on_the_boards_order(
        self, payload: dict[str, Any]
    ) -> None:
        """The order is undocumented and has no reason to be stable."""
        groups = payload["MBP_data_Market_Watch"]
        reversed_payload = {"MBP_data_Market_Watch": list(reversed(groups))}

        assert front_month(reversed_payload) == front_month(payload)

    def test_non_nifty_rows_are_ignored(self) -> None:
        body = {
            "MBP_data_Market_Watch": [
                {
                    "token_data": [
                        {
                            "SYMBOL": "SENSEX",
                            "INSTRUMENTTYPE": "FUTIDX",
                            "EXPIRYDATE": "01-Sep-2026",
                            "LASTPRICE": "1",
                        }
                    ]
                }
            ]
        }

        assert front_month(body) is None

    def test_an_empty_board_yields_nothing_rather_than_raising(self) -> None:
        assert front_month({"MBP_data_Market_Watch": []}) is None
        assert front_month({}) is None


class TestToQuote:
    def test_the_captured_row_maps_to_its_published_figures(
        self, payload: dict[str, Any]
    ) -> None:
        row = front_month(payload)
        assert row is not None

        quote = to_quote(row, fetched_at=NOW)

        assert quote.key == GIFT_KEY
        assert quote.price == Decimal("23267.50")
        assert quote.change == Decimal("-48.00")
        assert quote.change_percent == Decimal("-0.21")
        assert quote.provenance is not None
        assert quote.provenance.source is DataSource.LIVE

    def test_the_board_s_own_close_is_the_fallback_base(
        self, payload: dict[str, Any]
    ) -> None:
        """With no settlement to hand the board's figures are kept as-is.

        Imperfect - see the next test for why - but self-consistent, and it
        keeps the level on screen when the end-of-day file cannot be read.
        """
        row = front_month(payload)
        assert row is not None

        quote = to_quote(row, fetched_at=NOW)

        assert quote.previous_close == Decimal("23315.50")
        assert quote.price - quote.previous_close == quote.change

    def test_the_published_settlement_wins_over_the_board_s_close(
        self, payload: dict[str, Any]
    ) -> None:
        """The bug the card was reported for, with the day's real numbers.

        GIFT trades two sessions a day, and the board's ``CLOSE`` is struck
        against the session boundary rather than the trading day's. On
        28-Sep-2026 it read 23,236.00 where the exchange's own bhavcopy
        settled the same contract at 23,188.50 - which is the base every other
        screen in the market quotes the contract against.
        """
        row = front_month(payload)
        assert row is not None
        row = {**row, "LASTPRICE": "23140.50", "CLOSE": "23236.00", "CHANGE": "-95.50"}

        quote = to_quote(row, fetched_at=NOW, settlement=Decimal("23188.5"))

        assert quote.previous_close == Decimal("23188.5")
        assert quote.change == Decimal("-48.00")
        assert quote.change_percent == Decimal("-0.21")

    def test_the_change_is_recomputed_never_copied_beside_a_new_base(
        self, payload: dict[str, Any]
    ) -> None:
        """``CHANGE`` and ``PERCHANGE`` are struck against the board's own
        ``CLOSE``. Keeping them beside a different previous close would print
        a change that does not reconcile with the two levels next to it."""
        row = front_month(payload)
        assert row is not None

        quote = to_quote(row, fetched_at=NOW, settlement=Decimal("23200.00"))

        assert quote.change != Decimal(row["CHANGE"])
        assert quote.previous_close is not None
        assert quote.change is not None
        assert quote.price - quote.previous_close == quote.change

    def test_a_nonsense_settlement_falls_back_rather_than_dividing_by_zero(
        self, payload: dict[str, Any]
    ) -> None:
        row = front_month(payload)
        assert row is not None

        quote = to_quote(row, fetched_at=NOW, settlement=Decimal("0"))

        assert quote.previous_close == Decimal("23315.50")
        assert quote.change == Decimal("-48.00")

    def test_a_row_with_no_last_price_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="no last price"):
            to_quote({"EXPIRYDATE": "29-Sep-2026"}, fetched_at=NOW)
