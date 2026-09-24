"""The requested expiry has to reach FYERS, not just the label.

The bug this pins was invisible from the outside: the options-chain endpoint
selects a contract by ``timestamp``, that parameter was never sent, and the
mapper then stamped the *requested* expiry onto whatever near chain came back.
Every expiry returned the same book under a different heading - which on screen
looks exactly like a picker that does nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from marketcompass.contexts.market_data.domain.instruments import InstrumentSymbol
from marketcompass.infrastructure.brokers.fyers import client as fyers_client
from marketcompass.infrastructure.brokers.fyers.client import FyersMarketDataProvider
from marketcompass.infrastructure.brokers.fyers.option_chain_mapper import parse_expiry_epochs

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
NIFTY = InstrumentSymbol("NIFTY")


def _chain(*, oi: int) -> dict[str, Any]:
    """A minimal but structurally real options-chain response."""
    return {
        "data": {
            "expiryData": [
                {"date": "29-09-2026", "expiry": "1790000000"},
                {"date": "19-10-2026", "expiry": "1791728000"},
            ],
            "optionsChain": [
                {"strike_price": -1, "ltp": 23_115.0, "fp": 23_130.0},
                {"strike_price": 23_100, "option_type": "CE", "ltp": 120.0, "oi": oi},
                {"strike_price": 23_100, "option_type": "PE", "ltp": 95.0, "oi": oi * 2},
            ],
            "lotSize": 75,
        }
    }


class RecordingRest:
    """Records every timestamp asked for, and answers a different book each."""

    def __init__(self) -> None:
        self.timestamps: list[str] = []

    async def fetch_option_chain(
        self, *, app_id: str, access_token: str, symbol: str, strike_count: int = 20,
        timestamp: str = "",
    ) -> dict[str, Any]:
        self.timestamps.append(timestamp)
        # The far contract carries a visibly different book, so a test can tell
        # which one actually came back rather than trusting the label.
        return _chain(oi=500 if timestamp == "1791728000" else 9_000)


class NoQuota:
    async def acquire(self, app_id: str) -> None:
        return None


class NoBreaker:
    async def call(self, operation, description=""):  # type: ignore[no-untyped-def]
        return await operation()


class FixedClock:
    def now(self) -> datetime:
        return NOW


class Credentials:
    app_id = "app"
    secret = "s"


def _provider(rest: RecordingRest) -> FyersMarketDataProvider:
    return FyersMarketDataProvider(
        rest=rest,  # type: ignore[arg-type]
        credentials=Credentials(),  # type: ignore[arg-type]
        access_token="token",
        quota=NoQuota(),  # type: ignore[arg-type]
        breaker=NoBreaker(),  # type: ignore[arg-type]
        clock=FixedClock(),  # type: ignore[arg-type]
    )


@pytest.fixture(autouse=True)
def _clear_epoch_cache() -> None:
    fyers_client._EXPIRY_EPOCHS.clear()


class TestExpiryReachesTheBroker:
    """The target behaviour, not yet reached - see the xfails.

    Selecting an expiry needs the epoch FYERS publishes beside each date, and
    the live account's ``expiryData`` does not have the shape this adapter
    assumed, so the timestamp sent was ignored and the near chain came back. The
    adapter now reports the chain it actually got rather than mislabelling it.
    These stay as strict xfails so they flip to a failure the moment selection
    starts working and the code can be trusted again.
    """

    @pytest.mark.xfail(strict=True, reason="expiryData epoch shape not yet confirmed from a live payload")
    async def test_a_requested_expiry_is_sent_as_its_broker_timestamp(self) -> None:
        rest = RecordingRest()

        chain = await _provider(rest).get_option_chain(NIFTY, expiry="2026-10-19")

        # One call to learn the epoch map, then the real one for that contract.
        assert "1791728000" in rest.timestamps
        assert chain.expiry == "2026-10-19"

    @pytest.mark.xfail(strict=True, reason="expiryData epoch shape not yet confirmed from a live payload")
    async def test_the_far_contract_s_own_book_comes_back(self) -> None:
        """The assertion that would have caught the bug.

        Labelling is not enough: the rows have to be the far contract's. Here
        the near book carries 9,000 of open interest and the far one 500.
        """
        rest = RecordingRest()

        chain = await _provider(rest).get_option_chain(NIFTY, expiry="2026-10-19")

        call = chain.strikes[0].call
        assert call is not None
        assert call.open_interest == 500

    async def test_no_expiry_asked_for_takes_the_broker_s_default(self) -> None:
        rest = RecordingRest()

        chain = await _provider(rest).get_option_chain(NIFTY)

        assert rest.timestamps == [""]
        assert chain.expiry == "2026-09-29"

    async def test_an_unlisted_expiry_is_not_stamped_onto_the_default_chain(self) -> None:
        """The honest fallback.

        Serving the default chain is fine; calling it the expiry that was asked
        for is how one contract's rows end up under another's header.
        """
        rest = RecordingRest()

        chain = await _provider(rest).get_option_chain(NIFTY, expiry="2027-03-25")

        assert chain.expiry == "2026-09-29"


class TestExpiryEpochs:
    def test_the_broker_s_own_epoch_is_read_back_not_computed(self) -> None:
        """There is no documented rule for deriving it, and a guessed timestamp
        does not error - it silently returns the default chain."""
        epochs = parse_expiry_epochs(_chain(oi=1))

        assert epochs == {"2026-09-29": "1790000000", "2026-10-19": "1791728000"}

    def test_a_payload_without_expiry_data_yields_nothing(self) -> None:
        assert parse_expiry_epochs({"data": {}}) == {}
        assert parse_expiry_epochs({}) == {}
