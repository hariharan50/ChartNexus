"""The straddle replay, pinned to a table of verified numbers.

Every figure in :data:`TABLE` was taken candle by candle off the reference tool,
so these are not "what the code currently does" assertions — they are the
specification. A change that moves any of them has changed the product, not the
implementation.
"""

from __future__ import annotations

import pytest

from chartnexus.contexts.options_analytics.domain.oi_math import ChainRow
from chartnexus.contexts.options_analytics.domain.straddle_pnl import (
    ADJUSTMENT,
    ENTRY,
    EXIT,
    PnlFrame,
    simulate,
)
from chartnexus.shared_kernel.domain.errors import ValidationError

LOT_SIZE = 65
STEP = 50.0

#: ``(spot, {strike: (ce, pe)})`` per capture, from the reference run.
#:
#: Only two strikes are listed, which is enough for the at-the-money to land
#: where the reference put it at every row (22550 through i=5, 22500 from i=6)
#: while keeping every number in the fixture one the tool actually printed.
TABLE: list[tuple[float, dict[float, tuple[float, float]]]] = [
    (22544.50, {22550.0: (110.75, 82.95), 22500.0: (138.00, 65.00)}),
    (22544.45, {22550.0: (108.15, 83.20), 22500.0: (135.40, 65.20)}),
    (22560.65, {22550.0: (121.20, 77.70), 22500.0: (149.10, 60.30)}),
    (22557.05, {22550.0: (120.50, 77.55), 22500.0: (148.20, 60.45)}),
    (22553.00, {22550.0: (120.45, 77.35), 22500.0: (148.00, 60.25)}),
    (22541.25, {22550.0: (110.45, 84.60), 22500.0: (137.60, 66.40)}),
    (22517.80, {22550.0: (100.85, 97.60), 22500.0: (130.40, 77.25)}),
    (22523.95, {22550.0: (105.90, 93.10), 22500.0: (135.60, 73.20)}),
]

EXPECTED_HELD = [22550.0] * 6 + [22500.0, 22500.0]
EXPECTED_PNL = [0.00, 152.75, -338.00, -282.75, -266.50, -87.75, -308.75, -383.50]


def rows(book: dict[float, tuple[float, float]]) -> tuple[ChainRow, ...]:
    out: list[ChainRow] = []
    for strike, (ce, pe) in sorted(book.items()):
        out.append(ChainRow(strike=strike, option_type="CE", oi=0, oi_change=0, ltp=ce, volume=0))
        out.append(ChainRow(strike=strike, option_type="PE", oi=0, oi_change=0, ltp=pe, volume=0))
    return tuple(out)


def frames(
    table: list[tuple[float, dict[float, tuple[float, float]]]],
    *,
    session: str = "2026-10-05",
    start: int = 0,
) -> list[PnlFrame]:
    return [
        PnlFrame(
            session=session,
            timestamp=f"{session}T{9 + (start + i) // 60:02d}:{(15 + start + i) % 60:02d}:00+00:00",
            spot=spot,
            rows=rows(book),
        )
        for i, (spot, book) in enumerate(table)
    ]


def run(table=None, *, adjustment_points: float = 50.0, lots: int = 1, **kwargs):
    return simulate(
        frames(table if table is not None else TABLE),
        adjustment_points=adjustment_points,
        lot_size=LOT_SIZE,
        lots=lots,
        strike_step=STEP,
        **kwargs,
    )


class TestTheVerifiedTable:
    """The eight captures, row by row."""

    @pytest.mark.parametrize("index", range(len(TABLE)))
    def test_the_held_strike_matches_the_reference(self, index: int) -> None:
        assert run().series[index].entry_strike == EXPECTED_HELD[index]

    @pytest.mark.parametrize("index", range(len(TABLE)))
    def test_the_running_pnl_matches_the_reference(self, index: int) -> None:
        assert run().series[index].pnl == pytest.approx(EXPECTED_PNL[index])

    def test_the_summary_reports_the_curve_s_extremes(self) -> None:
        result = run()
        assert result.total_pnl == pytest.approx(-383.50)
        assert result.max_pnl == pytest.approx(152.75)
        assert result.min_pnl == pytest.approx(-383.50)
        assert result.total_adjustments == 1
        assert result.quantity == 65

    def test_the_synthetic_future_is_put_call_parity_on_the_held_strike(self) -> None:
        series = run().series
        assert series[0].synthetic_future == pytest.approx(22577.80)
        assert series[6].synthetic_future == pytest.approx(22553.15)


class TestTheTradeLog:
    def test_it_opens_sells_and_closes_exactly_once(self) -> None:
        assert [trade.type for trade in run().trades] == [ENTRY, ADJUSTMENT, EXIT]

    def test_the_entry_sells_the_at_the_money_straddle(self) -> None:
        entry = run().trades[0]
        assert entry.strike == 22550.0
        assert entry.straddle == pytest.approx(193.70)
        assert entry.cumulative_pnl == pytest.approx(0.0)

    def test_an_entry_books_no_leg_pnl_at_all(self) -> None:
        """``None``, not ``0.0`` — the log renders a dash, not a real-looking zero."""
        assert run().trades[0].leg_pnl is None

    def test_the_adjustment_closes_the_old_strike_and_opens_the_new(self) -> None:
        adjustment = run().trades[1]
        assert (adjustment.old_strike, adjustment.strike) == (22550.0, 22500.0)
        assert adjustment.exit_straddle == pytest.approx(198.45)
        assert adjustment.leg_pnl == pytest.approx(-308.75)
        assert adjustment.straddle == pytest.approx(207.65)
        assert adjustment.cumulative_pnl == pytest.approx(-308.75)

    def test_the_exit_books_the_rest(self) -> None:
        exit_trade = run().trades[-1]
        assert exit_trade.strike == 22500.0
        assert exit_trade.leg_pnl == pytest.approx(-74.75)
        assert exit_trade.cumulative_pnl == pytest.approx(-383.50)


class TestTheAdjustmentTrigger:
    def test_a_wider_threshold_never_fires_on_a_single_strike_move(self) -> None:
        """50 points of ATM travel is one strike; 100 demands two."""
        result = run(adjustment_points=100.0)
        assert result.total_adjustments == 0
        assert [trade.type for trade in result.trades] == [ENTRY, EXIT]
        assert all(point.entry_strike == 22550.0 for point in result.series)

    def test_the_trigger_reads_the_atm_strike_not_spot(self) -> None:
        """Spot moves 26.70 by i=6 — under 50 — yet the ATM moves a full strike.

        Comparing spot to the held strike would not have adjusted here at all,
        which is the single easiest way to get this engine subtly wrong.
        """
        assert abs(TABLE[6][0] - 22550.0) < 50.0
        assert run().total_adjustments == 1

    def test_an_adjustment_row_shows_the_new_strike_and_no_unrealised_pnl(self) -> None:
        point = run().series[6]
        assert point.entry_strike == 22500.0
        assert point.ce_price == pytest.approx(130.40)
        assert point.pe_price == pytest.approx(77.25)
        assert point.pnl == pytest.approx(-308.75)

    def test_the_running_count_is_carried_on_every_row(self) -> None:
        series = run().series
        assert [point.adjustments for point in series] == [0] * 6 + [1, 1]


#: A two-capture day whose second capture both re-strikes and closes.
CLOSING_ADJUSTMENT: list[tuple[float, dict[float, tuple[float, float]]]] = [
    (22544.50, {22550.0: (110.75, 82.95), 22500.0: (138.00, 65.00)}),
    (22517.80, {22550.0: (100.85, 97.60), 22500.0: (130.40, 77.25)}),
]


class TestAnAdjustmentOnTheClosingCapture:
    """The check runs on the last capture too, so both can share a timestamp."""

    def test_it_adjusts_and_then_exits(self) -> None:
        trades = run(CLOSING_ADJUSTMENT).trades
        assert [trade.type for trade in trades] == [ENTRY, ADJUSTMENT, EXIT]

    def test_the_exit_books_nothing_because_it_closes_what_just_opened(self) -> None:
        result = run(CLOSING_ADJUSTMENT)
        adjustment, exit_trade = result.trades[1], result.trades[2]
        assert exit_trade.leg_pnl == pytest.approx(0.0)
        assert exit_trade.t == adjustment.t
        assert exit_trade.cumulative_pnl == pytest.approx(adjustment.cumulative_pnl)


class TestSeveralSessions:
    def test_each_day_is_its_own_round_trip(self) -> None:
        two_days = frames(TABLE) + frames(TABLE, session="2026-10-06")
        result = simulate(
            two_days, adjustment_points=50.0, lot_size=LOT_SIZE, lots=1, strike_step=STEP
        )
        kinds = [trade.type for trade in result.trades]
        assert kinds.count(ENTRY) == 2
        assert kinds.count(EXIT) == 2

    def test_pnl_and_the_adjustment_count_carry_across_the_boundary(self) -> None:
        two_days = frames(TABLE) + frames(TABLE, session="2026-10-06")
        result = simulate(
            two_days, adjustment_points=50.0, lot_size=LOT_SIZE, lots=1, strike_step=STEP
        )
        # The second day repeats the first, so it ends at exactly twice the P&L
        # and twice the adjustments — the curve never resets.
        assert result.total_pnl == pytest.approx(-767.00)
        assert result.total_adjustments == 2
        assert result.series[-1].adjustments == 2
        assert result.sessions == ("2026-10-05", "2026-10-06")


class TestSizing:
    def test_lots_scale_the_pnl_linearly(self) -> None:
        result = run(lots=3)
        assert result.quantity == 195
        assert result.total_pnl == pytest.approx(-383.50 * 3)

    @pytest.mark.parametrize(("lot_size", "lots"), [(0, 1), (65, 0), (-1, 1)])
    def test_a_non_positive_size_is_rejected(self, lot_size: int, lots: int) -> None:
        with pytest.raises(ValidationError):
            simulate(frames(TABLE), adjustment_points=50.0, lot_size=lot_size, lots=lots)

    def test_a_non_positive_threshold_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            simulate(frames(TABLE), adjustment_points=0.0, lot_size=LOT_SIZE)


class TestMissingPrices:
    def test_a_day_with_no_captures_simulates_nothing(self) -> None:
        result = simulate([], adjustment_points=50.0, lot_size=LOT_SIZE)
        assert result.series == ()
        assert result.trades == ()
        assert result.quantity == 65

    def test_an_unquoted_leg_is_forward_filled_from_its_last_price(self) -> None:
        """A strike that drops out of the stored window keeps its last price."""
        gapped = [
            (22544.50, {22550.0: (110.75, 82.95), 22500.0: (138.00, 65.00)}),
            # 22550 unquoted here; the held straddle should hold its open value.
            (22546.00, {22550.0: (0.0, 0.0), 22500.0: (139.00, 64.00)}),
        ]
        result = run(gapped)
        assert result.series[1].straddle == pytest.approx(193.70)
        assert result.series[1].pnl == pytest.approx(0.0)

    def test_a_strike_never_priced_fails_loudly_naming_it(self) -> None:
        orphan = [(22544.50, {22550.0: (0.0, 0.0)})]
        with pytest.raises(ValidationError, match="22550"):
            run(orphan)
