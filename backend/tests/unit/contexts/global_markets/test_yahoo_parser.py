"""The Yahoo chart parser, against a real captured payload.

``gspc_chart.json`` is an actual 5-day S&P 500 response, saved unmodified. The
figures asserted below (7,706.03, -58.61, -0.755%) are the ones the reference
board printed for the same session, which is what makes this a test of the
mapping rather than of itself.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from marketcompass.contexts.global_markets.domain.quotes import DataSource
from marketcompass.infrastructure.global_markets.yahoo.chart_parser import (
    UnknownSymbolError,
    to_quote,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
FIXTURE = Path(__file__).parent / "gspc_chart.json"


@pytest.fixture
def payload() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestToQuote:
    def test_the_captured_payload_maps_to_the_published_figures(
        self, payload: dict[str, Any]
    ) -> None:
        quote = to_quote(payload, key="SPX", fetched_at=NOW)

        assert quote.price == Decimal("7706.03")
        assert quote.change == Decimal("-58.61")
        assert quote.change_percent == Decimal("-0.755")
        assert quote.provenance is not None
        assert quote.provenance.source is DataSource.LIVE

    def test_previous_close_is_derived_from_the_change_not_chart_previous_close(
        self, payload: dict[str, Any]
    ) -> None:
        """The subtle one.

        ``chartPreviousClose`` is the close before the *requested range*, so
        this same symbol reports 7,551.81 on a 5-day window and 7,764.70 on a
        2-day one. Reading it as "yesterday's close" would make the board
        disagree with itself whenever the range changed.
        """
        quote = to_quote(payload, key="SPX", fetched_at=NOW)

        assert payload["chart"]["result"][0]["meta"]["chartPreviousClose"] == 7551.81
        assert quote.previous_close == Decimal("7764.64")
        assert quote.price - quote.previous_close == quote.change

    def test_the_sparkline_drops_the_nulls(self, payload: dict[str, Any]) -> None:
        """A holiday arrives as ``null`` aligned with its timestamp. Plotting
        it as zero would draw a cliff to the axis that never happened."""
        closes = payload["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        assert None in closes

        quote = to_quote(payload, key="SPX", fetched_at=NOW)

        assert len(quote.spark) == len([value for value in closes if value is not None])
        assert quote.spark[-1] == Decimal("7706.02978515625")

    def test_the_last_print_is_dated(self, payload: dict[str, Any]) -> None:
        """The timeline needs this: a New York quote read at 06:00 IST belongs
        to yesterday's session there."""
        quote = to_quote(payload, key="SPX", fetched_at=NOW)

        assert quote.session is not None
        assert quote.session.tzinfo is not None

    def test_an_unknown_symbol_is_rejected_despite_a_200(self) -> None:
        """Yahoo answers an unknown symbol with HTTP 200 and an error body, so
        the status code is never trusted on its own."""
        body = {"chart": {"result": None, "error": {"code": "Not Found"}}}

        with pytest.raises(UnknownSymbolError):
            to_quote(body, key="NOPE", fetched_at=NOW)

    def test_a_quote_with_no_price_is_rejected(self) -> None:
        body = {"chart": {"result": [{"meta": {}}], "error": None}}

        with pytest.raises(UnknownSymbolError):
            to_quote(body, key="SPX", fetched_at=NOW)

    def test_a_percent_without_an_absolute_still_yields_a_previous_close(self) -> None:
        """Rather than leaving the board's previous-close column empty."""
        body = {
            "chart": {
                "result": [
                    {"meta": {"regularMarketPrice": 110, "regularMarketChangePercent": 10}}
                ],
                "error": None,
            }
        }

        quote = to_quote(body, key="X", fetched_at=NOW)

        assert quote.previous_close == Decimal("100.00")
        assert quote.change == Decimal("10.00")

    def test_a_missing_high_stays_missing(self) -> None:
        """Never zero: a market that published no high did not trade at zero."""
        body = {"chart": {"result": [{"meta": {"regularMarketPrice": 100}}], "error": None}}

        quote = to_quote(body, key="X", fetched_at=NOW)

        assert quote.day_high is None
        assert quote.day_low is None
        assert quote.spark == ()
