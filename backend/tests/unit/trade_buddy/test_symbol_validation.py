"""Reads and writes agree on which instruments exist.

The write bodies refused an unwatched instrument from the start. The query
strings did not, so `GET /state?symbol=RELIANCE` answered 200 with an empty
state — which reads as "no levels marked" when the truth is "never watched",
and contradicts the PUT that would have rejected the same value.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from chartnexus.contexts.trade_buddy.api.router import _watched_symbol
from chartnexus.contexts.trade_buddy.api.schemas import SetLevelsRequest, SetSettingsRequest
from chartnexus.contexts.trade_buddy.domain.instruments import (
    DEFAULT_SYMBOL,
    WATCHABLE,
    is_watchable,
    normalise,
)

pytestmark = pytest.mark.unit

UNWATCHED = ["RELIANCE", "NSE:NIFTY50-INDEX", "NIFTYBANK", "", "   "]


class TestTheWatchableSet:
    def test_it_is_the_three_indices(self):
        assert WATCHABLE == ("NIFTY", "BANKNIFTY", "SENSEX")
        assert DEFAULT_SYMBOL in WATCHABLE

    def test_the_broker_form_is_not_watchable(self):
        """Canonical names only. `NSE:NIFTY50-INDEX` is what the adapter sends
        to Fyers, never what this module keys state on."""
        assert is_watchable("NSE:NIFTY50-INDEX") is False
        assert is_watchable("NIFTY") is True

    def test_banknifty_is_canonical_not_the_broker_root(self):
        # The broker quotes it as NIFTYBANK; that string must never reach here.
        assert is_watchable("BANKNIFTY") is True
        assert is_watchable("NIFTYBANK") is False

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("nifty", "NIFTY"), (" banknifty ", "BANKNIFTY"), ("SenSex", "SENSEX")],
    )
    def test_normalising_is_case_and_space_insensitive(self, raw, expected):
        assert normalise(raw) == expected


class TestQueryParameter:
    @pytest.mark.parametrize("raw", ["NIFTY", "nifty", " banknifty ", "SENSEX"])
    def test_a_watched_instrument_is_canonicalised(self, raw):
        assert _watched_symbol(raw) == normalise(raw)

    @pytest.mark.parametrize("raw", UNWATCHED)
    def test_an_unwatched_instrument_is_refused(self, raw):
        with pytest.raises(HTTPException) as caught:
            _watched_symbol(raw)
        assert caught.value.status_code == 422

    def test_the_refusal_names_what_is_covered(self):
        """A bare rejection leaves the caller guessing; the message should not."""
        with pytest.raises(HTTPException) as caught:
            _watched_symbol("RELIANCE")
        detail = str(caught.value.detail)
        for symbol in WATCHABLE:
            assert symbol in detail

    def test_it_defaults_to_the_default_instrument(self):
        assert _watched_symbol() == DEFAULT_SYMBOL


class TestWriteBodies:
    """The halves that already validated, re-pinned so the two cannot drift."""

    @pytest.mark.parametrize("raw", ["RELIANCE", "NSE:NIFTY50-INDEX"])
    def test_set_levels_refuses_an_unwatched_instrument(self, raw):
        with pytest.raises(ValidationError, match="not watched"):
            SetLevelsRequest(
                symbol=raw,
                levels=[{"label": "R1", "price": 100.0, "role": "resistance"}],
            )

    def test_set_levels_canonicalises_a_watched_one(self):
        request = SetLevelsRequest(
            symbol="banknifty",
            levels=[{"label": "R1", "price": 52_000.0, "role": "resistance"}],
        )
        assert request.symbol == "BANKNIFTY"

    def test_set_settings_refuses_an_unwatched_instrument(self):
        with pytest.raises(ValidationError, match="not watched"):
            SetSettingsRequest(symbol="RELIANCE", overrides={})

    def test_reads_and_writes_accept_exactly_the_same_set(self):
        """The property that was broken: one half accepting what the other refuses."""
        for symbol in WATCHABLE:
            assert _watched_symbol(symbol) == symbol
            assert (
                SetLevelsRequest(
                    symbol=symbol,
                    levels=[{"label": "R1", "price": 100.0, "role": "resistance"}],
                ).symbol
                == symbol
            )

        for symbol in ["RELIANCE", "NIFTYBANK"]:
            with pytest.raises(HTTPException):
                _watched_symbol(symbol)
            with pytest.raises(ValidationError):
                SetLevelsRequest(
                    symbol=symbol,
                    levels=[{"label": "R1", "price": 100.0, "role": "resistance"}],
                )
