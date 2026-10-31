"""Reading prices out of Fyers frames, including the frames that lie.

The spec's instruction was to extract LTP defensively because the key varies
between litemode and full mode. These tests encode the stronger rule the module
actually follows: when the frame does not clearly carry a price, return nothing.
A fabricated price here becomes a false break alert, which is the single worst
output this feature can produce.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from chartnexus.infrastructure.brokers.fyers.tick_parsing import (
    extract_price,
    extract_symbol,
    extract_time,
)

pytestmark = pytest.mark.unit

FALLBACK = datetime(2026, 10, 26, 4, 30, tzinfo=UTC)


class TestExtractPrice:
    @pytest.mark.parametrize(
        "frame",
        [
            {"ltp": 24_650.5},
            {"last_price": 24_650.5},
            {"lp": 24_650.5},
            {"LTP": 24_650.5},
            {"last_traded_price": 24_650.5},
        ],
    )
    def test_each_known_key_is_read(self, frame):
        assert extract_price(frame) == 24_650.5

    def test_a_string_price_is_coerced(self):
        """Fyers has sent numerics as strings; rejecting them would drop ticks."""
        assert extract_price({"ltp": "24650.5"}) == 24_650.5

    def test_the_first_trusted_key_wins(self):
        assert extract_price({"ltp": 100.0, "last_price": 200.0}) == 100.0

    @pytest.mark.parametrize(
        "frame",
        [
            {},
            {"ltp": None},
            {"ltp": 0},
            {"ltp": -5.0},
            {"ltp": "not a number"},
            {"ltp": ""},
            {"volume": 1000},
            {"ltp": [1, 2]},
            {"ltp": {"nested": 1}},
        ],
    )
    def test_an_untrustworthy_frame_yields_none(self, frame):
        assert extract_price(frame) is None

    def test_a_bool_is_not_a_price(self):
        """``float(True)`` is 1.0 — a flag in a price field must not become ₹1."""
        assert extract_price({"ltp": True}) is None

    @pytest.mark.parametrize("frame", [None, "string", 42, [], ("ltp", 1)])
    def test_a_non_dict_message_yields_none(self, frame):
        assert extract_price(frame) is None

    def test_it_falls_through_to_a_later_key_when_the_first_is_bad(self):
        assert extract_price({"ltp": 0, "last_price": 24_700.0}) == 24_700.0


class TestExtractSymbol:
    @pytest.mark.parametrize("key", ["symbol", "Symbol", "s", "ticker"])
    def test_each_known_key_is_read(self, key):
        assert extract_symbol({key: "NSE:NIFTY50-INDEX"}) == "NSE:NIFTY50-INDEX"

    def test_whitespace_is_trimmed(self):
        assert extract_symbol({"symbol": "  NSE:NIFTY50-INDEX  "}) == "NSE:NIFTY50-INDEX"

    @pytest.mark.parametrize("frame", [{}, {"symbol": ""}, {"symbol": "   "}, {"symbol": 5}])
    def test_a_missing_or_blank_symbol_yields_none(self, frame):
        assert extract_symbol(frame) is None


class TestExtractTime:
    def test_a_sane_epoch_is_used(self):
        moment = datetime(2026, 10, 26, 5, 0, tzinfo=UTC)
        frame = {"last_traded_time": moment.timestamp()}
        assert extract_time(frame, fallback=FALLBACK) == moment

    @pytest.mark.parametrize("key", ["last_traded_time", "exch_feed_time", "timestamp", "tt"])
    def test_each_known_key_is_read(self, key):
        moment = datetime(2026, 10, 26, 5, 0, tzinfo=UTC)
        assert extract_time({key: moment.timestamp()}, fallback=FALLBACK) == moment

    @pytest.mark.parametrize(
        "frame",
        [
            {},
            {"last_traded_time": 0},
            {"last_traded_time": -1},
            {"last_traded_time": "nonsense"},
            {"last_traded_time": None},
            {"last_traded_time": 1},  # 1970 — a clock bug, not a trade
            {"last_traded_time": 99_999_999_999_999},  # far future
        ],
    )
    def test_an_implausible_timestamp_falls_back_to_arrival(self, frame):
        """Keying the daily cap to 1970 would break the session-gap check."""
        assert extract_time(frame, fallback=FALLBACK) == FALLBACK

    def test_a_non_dict_message_falls_back(self):
        assert extract_time(None, fallback=FALLBACK) == FALLBACK

    def test_the_result_is_always_timezone_aware(self):
        """Naive datetimes are a banned class in this codebase (ruff DTZ)."""
        moment = datetime(2026, 10, 26, 5, 0, tzinfo=UTC)
        assert extract_time({"tt": moment.timestamp()}, fallback=FALLBACK).tzinfo is not None
        assert extract_time({}, fallback=FALLBACK).tzinfo is not None
