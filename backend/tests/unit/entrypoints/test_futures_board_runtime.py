"""The futures-board capture: what it will and will not put in the archive.

A stored frame outlives the process that wrote it, and nothing downstream can
tell a mislabelled one from a real one. These cover the rules that keep the
archive trustworthy.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from chartnexus.contexts.futures_analytics.application.ports import BoardSnapshot
from chartnexus.contexts.futures_analytics.domain.buildup import FuturesReading
from chartnexus.entrypoints.futures_board_runtime import (
    _bucket,
    frames_from,
    session_date_of,
)

pytestmark = pytest.mark.unit

AT = datetime(2026, 9, 21, 8, 30, tzinfo=UTC)
_IST = timezone(timedelta(hours=5, minutes=30))


def reading(symbol: str = "RELIANCE", *, price: str = "1250") -> FuturesReading:
    return FuturesReading(
        symbol=symbol,
        price=Decimal(price),
        price_open=Decimal("1200"),
        open_interest=110_000,
        open_interest_open=100_000,
        expiry="2026-09-29",
        volume=5_000,
    )


def test_a_live_board_becomes_frames() -> None:
    snapshot = BoardSnapshot(readings=[reading(), reading("TCS")], source="live")

    frames = frames_from(snapshot, AT)

    assert [frame.symbol for frame in frames] == ["RELIANCE", "TCS"]
    assert all(frame.source == "live" for frame in frames)
    assert all(frame.captured_at == AT for frame in frames)
    assert frames[0].open_interest == 110_000
    assert frames[0].expiry == "2026-09-29"


def test_a_mock_board_is_never_archived() -> None:
    """The one rule the whole archive rests on.

    A generated session stored as live cannot be distinguished later, and every
    chart drawn from it would be a confident lie.
    """
    snapshot = BoardSnapshot(readings=[reading()], source="mock")

    assert frames_from(snapshot, AT) == []


def test_a_contract_the_board_could_not_price_is_dropped_not_zeroed() -> None:
    snapshot = BoardSnapshot(readings=[reading(), reading("GHOST", price="0")], source="live")

    frames = frames_from(snapshot, AT)

    assert [frame.symbol for frame in frames] == ["RELIANCE"]


def test_an_empty_board_yields_nothing_rather_than_failing() -> None:
    assert frames_from(BoardSnapshot(source="live"), AT) == []


def test_the_session_date_is_the_exchanges_not_utcs() -> None:
    """20:00 UTC is already tomorrow in IST.

    Storing the UTC date would file the last ninety minutes of every session
    under the previous day.
    """
    assert session_date_of(datetime(2026, 9, 21, 20, 0, tzinfo=UTC)) == date(2026, 9, 22)
    assert session_date_of(datetime(2026, 9, 21, 8, 30, tzinfo=UTC)) == date(2026, 9, 21)


def test_frames_are_stamped_with_the_exchange_date_of_their_capture() -> None:
    late = datetime(2026, 9, 21, 20, 0, tzinfo=UTC)

    frames = frames_from(BoardSnapshot(readings=[reading()], source="live"), late)

    assert frames[0].session_date == date(2026, 9, 22)


@pytest.mark.parametrize(
    ("second", "interval", "expected"),
    [
        (0, 60, 0),
        (59, 60, 0),
        (61, 60, 60),
        (299, 300, 0),
        (301, 300, 300),
    ],
)
def test_a_capture_is_floored_onto_its_cadence(second: int, interval: int, expected: int) -> None:
    """So a restarted worker re-capturing an interval collides with what is
    already stored, instead of crowding the series with a near-duplicate."""
    base = datetime(2026, 9, 21, 8, 0, tzinfo=UTC)

    bucketed = _bucket(base + timedelta(seconds=second), interval)

    assert bucketed == base + timedelta(seconds=expected)


def test_bucketing_survives_a_nonsense_interval() -> None:
    moment = datetime(2026, 9, 21, 8, 0, 30, tzinfo=UTC)

    assert _bucket(moment, 0) == moment.replace(microsecond=0)
