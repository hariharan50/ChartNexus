"""The pure open-interest derivations.

These are the numbers every Options Lab page agrees on, so they are pinned
directly rather than only through the services that call them.
"""

from __future__ import annotations

import math

from chartnexus.contexts.options_analytics.domain.oi_math import (
    ChainRow,
    atm_strike,
    max_pain,
    pcr_oi,
    rows_within,
    strike_window,
)


def _row(side: str, strike: float, oi: int = 0) -> ChainRow:
    return ChainRow(strike=strike, option_type=side, oi=oi, oi_change=0, ltp=10.0, volume=0)


# -- pcr --------------------------------------------------------------------


def test_pcr_is_puts_over_calls() -> None:
    rows = [_row("CE", 100.0, oi=200), _row("PE", 100.0, oi=300)]

    assert pcr_oi(rows) == 1.5


def test_pcr_with_no_call_interest_is_zero_not_an_infinity() -> None:
    """A headline figure has to render something; the *line* charts use None instead."""
    assert pcr_oi([_row("PE", 100.0, oi=300)]) == 0.0


# -- atm --------------------------------------------------------------------


def test_atm_is_the_listed_strike_nearest_spot() -> None:
    assert atm_strike(24_662.0, [24_600.0, 24_650.0, 24_700.0]) == 24_650.0


def test_atm_falls_back_to_rounding_when_nothing_is_listed() -> None:
    assert atm_strike(24_662.0, [], step=50.0) == 24_650.0


# -- the strike window ------------------------------------------------------


def test_the_window_is_measured_in_steps_not_points() -> None:
    """A span of 10 is 500 points on NIFTY and 1000 on BANKNIFTY."""
    assert strike_window(atm=24_650.0, step=50.0, span=10) == (24_150.0, 25_150.0)
    assert strike_window(atm=52_000.0, step=100.0, span=10) == (51_000.0, 53_000.0)


def test_no_span_means_the_whole_chain_rather_than_an_arbitrary_width() -> None:
    """Widening to infinity leaves callers with one filter and no special case."""
    low, high = strike_window(atm=24_650.0, step=50.0, span=None)

    assert math.isinf(low) and low < 0
    assert math.isinf(high) and high > 0


def test_rows_within_keeps_the_edge_strike() -> None:
    """Float ladders make the boundary strike drop out at random without a tolerance.

    ``24_500 - 3 * 50`` is not always bit-identical to the ``24_350.0`` the
    broker sent, and the visible effect is an OI total that jitters as the
    window's edge leg blinks in and out.
    """
    rows = [_row("PE", 24_500.0 - index * 50.0) for index in range(4)]
    low, high = strike_window(atm=24_500.0, step=50.0, span=3)

    assert len(rows_within(rows, low, high)) == 4


def test_rows_outside_the_window_are_dropped() -> None:
    rows = [_row("PE", 24_000.0), _row("PE", 24_650.0), _row("PE", 30_000.0)]

    kept = rows_within(rows, 24_600.0, 24_700.0)

    assert [row.strike for row in kept] == [24_650.0]


# -- max pain ---------------------------------------------------------------


def test_max_pain_is_where_writers_owe_least() -> None:
    """All the open interest sits at one strike, so that strike is the least painful."""
    strikes = [24_600.0, 24_650.0, 24_700.0]
    rows = [_row("CE", 24_650.0, oi=1_000), _row("PE", 24_650.0, oi=1_000)]

    assert max_pain(rows, strikes) == 24_650.0


def test_max_pain_with_nothing_to_price_is_zero() -> None:
    assert max_pain([], [24_650.0]) == 0.0
    assert max_pain([_row("CE", 24_650.0, oi=10)], []) == 0.0
