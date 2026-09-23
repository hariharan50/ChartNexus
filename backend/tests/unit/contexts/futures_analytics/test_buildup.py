"""The 2x2 that the Future Dashboard is built on."""

from __future__ import annotations

from decimal import Decimal

import pytest

from marketcompass.contexts.futures_analytics.domain.buildup import (
    BuildupState,
    FuturesReading,
    classify,
    in_state,
    to_rows,
    top_gainers,
    top_losers,
)

pytestmark = pytest.mark.unit


def reading(
    symbol: str = "RELIANCE",
    *,
    price: str = "100",
    price_open: str = "100",
    oi: int = 1000,
    oi_open: int = 1000,
) -> FuturesReading:
    return FuturesReading(
        symbol=symbol,
        price=Decimal(price),
        price_open=Decimal(price_open),
        open_interest=oi,
        open_interest_open=oi_open,
    )


# -- the truth table --------------------------------------------------------


@pytest.mark.parametrize(
    ("price", "oi", "expected"),
    [
        ("110", 1100, BuildupState.LONG_BUILDUP),  # price up,   OI up
        ("90", 1100, BuildupState.SHORT_BUILDUP),  # price down, OI up
        ("110", 900, BuildupState.SHORT_COVERING),  # price up,   OI down
        ("90", 900, BuildupState.LONG_UNWINDING),  # price down, OI down
    ],
)
def test_every_quadrant(price: str, oi: int, expected: BuildupState) -> None:
    assert classify(reading(price=price, oi=oi)) is expected


def test_a_flat_contract_is_neutral_not_a_fifth_quadrant() -> None:
    assert classify(reading()) is BuildupState.NEUTRAL


@pytest.mark.parametrize(
    ("price", "oi"),
    [
        ("100.01", 1100),  # price barely moved
        ("110", 1000),  # OI barely moved
    ],
)
def test_a_move_inside_the_deadband_is_not_a_signal(price: str, oi: int) -> None:
    """A contract that ticked a paisa is not "building longs"."""
    assert classify(reading(price=price, oi=oi)) is BuildupState.NEUTRAL


def test_the_deadband_is_tunable() -> None:
    quiet = reading(price="100.5", oi=1005)  # 0.5% on both axes

    assert classify(quiet) is BuildupState.LONG_BUILDUP
    assert classify(quiet, deadband_percent=Decimal(1)) is BuildupState.NEUTRAL


# -- missing baselines ------------------------------------------------------


def test_a_contract_with_no_opening_price_is_not_classified() -> None:
    """No baseline is not the same as no movement."""
    row = to_rows([reading(price="110", price_open="0", oi=1100)])[0]

    assert row.price_change_percent is None
    assert row.state is BuildupState.NEUTRAL


def test_a_contract_with_no_opening_oi_is_not_classified() -> None:
    row = to_rows([reading(price="110", oi=1100, oi_open=0)])[0]

    assert row.oi_change_percent is None
    assert row.state is BuildupState.NEUTRAL


def test_rows_without_a_baseline_are_excluded_from_rankings_not_sorted_as_zero() -> None:
    rows = to_rows(
        [
            reading("UP", price="110", oi=1100),
            reading("DOWN", price="90", oi=1100),
            reading("UNKNOWN", price="105", price_open="0"),
        ]
    )

    assert [row.symbol for row in top_gainers(rows, limit=10)] == ["UP", "DOWN"]
    assert [row.symbol for row in top_losers(rows, limit=10)] == ["DOWN", "UP"]


# -- ranking ----------------------------------------------------------------


def test_gainers_and_losers_rank_by_price_move() -> None:
    rows = to_rows(
        [
            reading("SMALL", price="101", oi=1100),
            reading("BIG", price="120", oi=1100),
            reading("DROP", price="80", oi=1100),
        ]
    )

    assert [row.symbol for row in top_gainers(rows, limit=2)] == ["BIG", "SMALL"]
    assert [row.symbol for row in top_losers(rows, limit=2)] == ["DROP", "SMALL"]


def test_a_state_bucket_ranks_by_open_interest_not_price() -> None:
    """ "Which contracts are seeing the most fresh shorts" is an OI question."""
    rows = to_rows(
        [
            # Falls furthest, but only a little fresh OI.
            reading("BIGPRICEDROP", price="50", oi=1010),
            # Barely falls, but OI doubles — this is the stronger short buildup.
            reading("BIGOIJUMP", price="99", oi=2000),
        ]
    )

    ranked = in_state(rows, BuildupState.SHORT_BUILDUP, limit=5)

    assert [row.symbol for row in ranked] == ["BIGOIJUMP", "BIGPRICEDROP"]


def test_an_unwinding_bucket_ranks_by_the_largest_fall_in_open_interest() -> None:
    rows = to_rows(
        [
            reading("SMALLEXIT", price="90", oi=990),
            reading("BIGEXIT", price="90", oi=500),
        ]
    )

    ranked = in_state(rows, BuildupState.LONG_UNWINDING, limit=5)

    assert [row.symbol for row in ranked] == ["BIGEXIT", "SMALLEXIT"]


def test_a_bucket_only_contains_its_own_state() -> None:
    rows = to_rows(
        [
            reading("LONGS", price="110", oi=1100),
            reading("SHORTS", price="90", oi=1100),
        ]
    )

    assert [r.symbol for r in in_state(rows, BuildupState.LONG_BUILDUP, limit=5)] == ["LONGS"]
    assert [r.symbol for r in in_state(rows, BuildupState.SHORT_BUILDUP, limit=5)] == ["SHORTS"]


def test_limits_are_honoured() -> None:
    rows = to_rows([reading(f"S{n}", price=str(100 + n), oi=1100) for n in range(1, 20)])

    assert len(top_gainers(rows, limit=5)) == 5
    assert len(in_state(rows, BuildupState.LONG_BUILDUP, limit=3)) == 3


# -- the open marker --------------------------------------------------------


def with_prints(*, day_open: str | None, high: str = "110", low: str = "90") -> FuturesReading:
    return FuturesReading(
        symbol="RELIANCE",
        price=Decimal(100),
        price_open=Decimal(100),
        open_interest=1000,
        open_interest_open=1000,
        day_open=Decimal(day_open) if day_open is not None else None,
        day_high=Decimal(high),
        day_low=Decimal(low),
    )


def test_opening_on_the_low_is_marked() -> None:
    """Never traded below the open: every buyer since the bell is in profit."""
    assert with_prints(day_open="90").open_marker == "O=L"


def test_opening_on_the_high_is_marked() -> None:
    assert with_prints(day_open="110").open_marker == "O=H"


def test_opening_inside_the_range_is_not_marked() -> None:
    assert with_prints(day_open="100").open_marker is None


@pytest.mark.parametrize("missing", ["open", "high", "low"])
def test_a_missing_print_makes_the_question_unanswerable(missing: str) -> None:
    """Unanswerable, not false — the badge must be absent, not negative."""
    kwargs: dict[str, str | None] = {"day_open": "90", "high": "110", "low": "90"}
    kwargs["day_open" if missing == "open" else missing] = None
    reading = FuturesReading(
        symbol="RELIANCE",
        price=Decimal(100),
        price_open=Decimal(100),
        open_interest=1000,
        open_interest_open=1000,
        day_open=Decimal(kwargs["day_open"]) if kwargs["day_open"] else None,
        day_high=Decimal(kwargs["high"]) if kwargs["high"] else None,
        day_low=Decimal(kwargs["low"]) if kwargs["low"] else None,
    )
    assert reading.open_marker is None


# -- volume change ----------------------------------------------------------


def with_volume(*, volume: int | None, previous: int | None) -> FuturesReading:
    return FuturesReading(
        symbol="RELIANCE",
        price=Decimal(100),
        price_open=Decimal(100),
        open_interest=1000,
        open_interest_open=1000,
        volume=volume,
        volume_open=previous,
    )


def test_volume_change_is_a_percentage_of_yesterday() -> None:
    assert with_volume(volume=150, previous=100).volume_change_percent == Decimal(50)


@pytest.mark.parametrize(
    ("volume", "previous"),
    [(None, 100), (150, None), (150, 0)],
)
def test_volume_change_is_null_when_there_is_nothing_to_compare(
    volume: int | None, previous: int | None
) -> None:
    """The live broker payload carries no previous-day volume, so this is the
    normal case in production. It must never read as 0.00%."""
    assert with_volume(volume=volume, previous=previous).volume_change_percent is None


def test_the_row_carries_both_derivations() -> None:
    row = to_rows(
        [
            FuturesReading(
                symbol="RELIANCE",
                price=Decimal(110),
                price_open=Decimal(100),
                open_interest=1100,
                open_interest_open=1000,
                volume=150,
                volume_open=100,
                day_open=Decimal(90),
                day_high=Decimal(110),
                day_low=Decimal(90),
            )
        ]
    )[0]

    assert row.open_marker == "O=L"
    assert row.volume_change_percent == Decimal(50)
