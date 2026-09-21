"""Chunking the quote request.

The whole reason the Future Dashboard is affordable. The broker quota is 8
requests/second and 100k/day, shared by ingest, every user request and every
agent; asking for 219 contracts one at a time would spend a fifth of the daily
budget on one page refresh.
"""

from __future__ import annotations

import pytest

from marketcompass.infrastructure.brokers.fyers.futures_mapper import split_quote_batch
from marketcompass.infrastructure.brokers.fyers.rest_client import (
    QUOTE_BATCH_SIZE,
    batch_symbols,
)

pytestmark = pytest.mark.unit


def test_the_universe_becomes_a_handful_of_requests() -> None:
    symbols = [f"NSE:SYM{n}26SEPFUT" for n in range(219)]

    batches = batch_symbols(symbols)

    assert len(batches) == 5  # not 219
    assert all(len(batch) <= QUOTE_BATCH_SIZE for batch in batches)
    assert sum(len(batch) for batch in batches) == 219


def test_order_is_preserved_across_batches() -> None:
    symbols = [f"S{n}" for n in range(10)]

    assert [s for batch in batch_symbols(symbols, 3) for s in batch] == symbols


def test_duplicates_are_dropped_rather_than_wasting_a_slot() -> None:
    """The response is keyed by symbol, so asking twice buys nothing."""
    assert batch_symbols(["A", "B", "A", "C", "B"], 10) == [["A", "B", "C"]]


def test_an_exact_multiple_does_not_produce_a_trailing_empty_batch() -> None:
    assert batch_symbols(["A", "B", "C", "D"], 2) == [["A", "B"], ["C", "D"]]


def test_no_symbols_means_no_requests() -> None:
    assert batch_symbols([]) == []


def test_a_nonsensical_batch_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        batch_symbols(["A"], 0)


# -- unpacking the response -------------------------------------------------


def test_a_batch_response_is_split_by_symbol() -> None:
    payload = {
        "d": [
            {"n": "NSE:RELIANCE26SEPFUT", "v": {"lp": 1270}},
            {"n": "NSE:TCS26SEPFUT", "v": {"lp": 3200}},
        ]
    }

    quotes = split_quote_batch(payload)

    assert set(quotes) == {"NSE:RELIANCE26SEPFUT", "NSE:TCS26SEPFUT"}
    assert quotes["NSE:TCS26SEPFUT"]["lp"] == 3200


def test_an_unusable_entry_does_not_lose_the_rest_of_the_batch() -> None:
    """One unquotable contract must not cost the other forty-nine."""
    payload = {
        "d": [
            {"n": "NSE:GOOD26SEPFUT", "v": {"lp": 100}},
            {"n": "NSE:NOVALUES26SEPFUT"},  # no `v`
            "not even a dict",
            {"v": {"lp": 5}},  # no symbol to key it by
        ]
    }

    assert set(split_quote_batch(payload)) == {"NSE:GOOD26SEPFUT"}


@pytest.mark.parametrize("payload", [{}, {"d": None}, {"d": "nope"}])
def test_a_malformed_response_yields_nothing_rather_than_raising(payload: dict) -> None:
    """A board is assembled from whatever came back; there is no single quote
    whose absence should abort it."""
    assert split_quote_batch(payload) == {}
