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

    def test_close_is_the_previous_settlement_not_the_live_price(
        self, payload: dict[str, Any]
    ) -> None:
        """Conflating the two would put the basis out by a full session."""
        row = front_month(payload)
        assert row is not None

        quote = to_quote(row, fetched_at=NOW)

        assert quote.previous_close == Decimal("23315.50")
        assert quote.price != quote.previous_close
        assert quote.price - quote.previous_close == quote.change

    def test_a_row_with_no_last_price_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="no last price"):
            to_quote({"EXPIRYDATE": "29-Sep-2026"}, fetched_at=NOW)
