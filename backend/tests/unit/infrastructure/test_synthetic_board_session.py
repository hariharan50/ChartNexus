"""Fabricated futures-board sessions.

The archive is read as fact. These cover the properties that keep a seeded day
separable from a captured one.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone
from itertools import pairwise

import pytest

from marketcompass.infrastructure.ingestion.synthetic_board_session import (
    build_synthetic_board_session,
)

pytestmark = pytest.mark.unit

_IST = timezone(timedelta(hours=5, minutes=30))
SESSION = date(2026, 9, 18)


def build(**kwargs: object) -> list:
    defaults: dict = {
        "symbol": "RELIANCE",
        "session_date": SESSION,
        "expiry": "2026-09-29",
        "interval_seconds": 60,
    }
    return build_synthetic_board_session(**{**defaults, **kwargs})  # type: ignore[arg-type]


def test_every_fabricated_frame_is_stamped_mock() -> None:
    """The one property that keeps the archive trustworthy.

    A seeded frame stored as live could never be told apart afterwards, and
    every chart drawn over it would be a confident invention.
    """
    frames = build()

    assert frames
    assert {frame.source for frame in frames} == {"mock"}


def test_a_whole_session_runs_from_the_bell_to_the_close() -> None:
    frames = build()

    first = frames[0].captured_at.astimezone(_IST)
    last = frames[-1].captured_at.astimezone(_IST)
    assert (first.hour, first.minute) == (9, 15)
    assert (last.hour, last.minute) == (15, 30)


def test_the_interval_sets_the_spacing() -> None:
    frames = build(interval_seconds=300)

    gaps = {
        (b.captured_at - a.captured_at).total_seconds()
        for a, b in pairwise(frames)
    }
    assert gaps == {300.0}


def test_todays_session_is_clipped_to_now() -> None:
    """The archive must not claim captures that have not happened yet."""
    noon = datetime.combine(SESSION, time(12, 0), tzinfo=_IST).astimezone(UTC)

    frames = build(until=noon)

    assert frames[-1].captured_at <= noon
    assert frames[-1].captured_at.astimezone(_IST).hour == 12


def test_a_session_date_is_the_exchanges_not_utcs() -> None:
    frames = build()

    assert {frame.session_date for frame in frames} == {SESSION}
    # 09:15 IST is 03:45 the same UTC day, so the two happen to agree here —
    # what matters is that the stamp follows the session, not the instant.
    assert frames[0].captured_at.astimezone(UTC).hour == 3


def test_frames_carry_the_contract_they_priced() -> None:
    frames = build(expiry="2026-09-29")

    assert {frame.expiry for frame in frames} == {"2026-09-29"}


def test_a_contract_with_no_known_expiry_still_seeds() -> None:
    """The catalog can legitimately hold no front expiry; that is not a reason
    to leave the day empty."""
    frames = build(expiry=None)

    assert frames
    assert frames[0].expiry is None


def test_prices_and_open_interest_are_positive_throughout() -> None:
    frames = build(interval_seconds=900)

    assert all(frame.price > 0 for frame in frames)
    assert all(frame.open_interest is not None for frame in frames)
    assert all((frame.open_interest or 0) > 0 for frame in frames)


def test_a_seeded_session_is_reproducible() -> None:
    """Re-seeding the same day must not invent a different history.

    The mock simulation is seeded from the symbol and date, so the second run
    reproduces the first — which is what makes ``--replace`` safe.
    """
    first = build(interval_seconds=900)
    second = build(interval_seconds=900)

    assert [f.price for f in first] == [f.price for f in second]
    assert [f.open_interest for f in first] == [f.open_interest for f in second]


def test_two_contracts_do_not_share_one_history() -> None:
    reliance = build(symbol="RELIANCE", interval_seconds=900)
    mm = build(symbol="M&M", interval_seconds=900)

    assert [f.price for f in reliance] != [f.price for f in mm]
