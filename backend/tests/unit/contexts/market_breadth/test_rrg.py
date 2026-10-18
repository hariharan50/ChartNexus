"""The rotation plane, from price series to tail.

Every assertion here is about a number that cannot be eyeballed off the chart.
An RRG that is subtly wrong still draws twelve tidy tails rotating clockwise —
the failure modes are an axis that is a z-score of the wrong window, a
composite that lets the most expensive member set the sector's move, and
stamps that align from the left so every tail is labelled with the time of a
point drawn somewhere else entirely.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from chartnexus.contexts.market_breadth.domain.rotation import Quadrant
from chartnexus.contexts.market_breadth.domain.rrg import (
    classify,
    composite,
    momentum,
    normalise,
    relative_strength,
    rotation,
    smooth,
)

pytestmark = pytest.mark.unit

START = datetime(2026, 10, 16, 3, 45, tzinfo=UTC)


def stamps(count: int) -> list[datetime]:
    return [START + timedelta(minutes=15 * step) for step in range(count)]


class TestClassify:
    """The quadrant rule, including the boundary nobody agrees on by accident."""

    @pytest.mark.parametrize(
        ("ratio", "mom", "expected"),
        [
            (101.0, 101.0, Quadrant.LEADING),
            (101.0, 99.0, Quadrant.WEAKENING),
            (99.0, 99.0, Quadrant.LAGGING),
            (99.0, 101.0, Quadrant.IMPROVING),
        ],
    )
    def test_each_corner(self, ratio: float, mom: float, expected: Quadrant) -> None:
        assert classify(ratio, mom) is expected

    def test_the_axes_belong_to_the_stronger_reading(self) -> None:
        # Exactly 100 is "not yet weakening", not "already lagging". Stated in
        # one place so two call sites cannot disagree about the cross.
        assert classify(100.0, 100.0) is Quadrant.LEADING
        assert classify(100.0, 99.9) is Quadrant.WEAKENING
        assert classify(99.9, 100.0) is Quadrant.IMPROVING


class TestRelativeStrength:
    def test_is_a_percentage_of_the_benchmark(self) -> None:
        rs = relative_strength([Decimal(110), Decimal(120)], [Decimal(100), Decimal(100)])
        assert rs == pytest.approx([110.0, 120.0])

    def test_a_broken_benchmark_capture_yields_no_point(self) -> None:
        # Zero is not a price. Carrying it forward would plant the same spike
        # in the middle of every sector's tail at once.
        rs = relative_strength([Decimal(110), Decimal(120)], [Decimal(0), Decimal(100)])
        assert rs == pytest.approx([120.0])


class TestNormalise:
    def test_drops_the_periods_with_no_full_lookback(self) -> None:
        # Twenty periods, window of fourteen, so the first thirteen go.
        assert len(normalise([float(n) for n in range(20)], window=14)) == 7

    def test_too_short_a_series_measures_nothing(self) -> None:
        assert normalise([1.0, 2.0, 3.0], window=14) == []

    def test_a_flat_series_sits_dead_centre(self) -> None:
        # Zero spread would divide by zero; flat against the benchmark is 100
        # by definition rather than an infinity.
        assert normalise([5.0] * 20, window=14) == [100.0] * 7

    def test_rising_relative_strength_reads_above_a_hundred(self) -> None:
        rising = normalise([float(n) for n in range(20)], window=14)
        assert all(value > 100.0 for value in rising)

    def test_falling_relative_strength_reads_below(self) -> None:
        falling = normalise([float(20 - n) for n in range(20)], window=14)
        assert all(value < 100.0 for value in falling)


class TestSmooth:
    def test_shortens_by_the_span(self) -> None:
        assert smooth([1.0, 2.0, 3.0, 4.0], span=3) == [2.0, 3.0]

    def test_a_span_of_one_is_a_passthrough(self) -> None:
        assert smooth([1.0, 2.0], span=1) == [1.0, 2.0]


class TestMomentum:
    def test_is_a_ratio_of_where_it_stood(self) -> None:
        assert momentum([100.0, 100.0, 100.0, 100.0, 110.0], span=4) == pytest.approx([110.0])

    def test_needs_more_periods_than_the_span(self) -> None:
        assert momentum([100.0] * 4, span=4) == []


class TestComposite:
    def test_rebases_each_member_before_averaging(self) -> None:
        # The whole point: a 4,000-rupee name and a 200-rupee one that both
        # rise 10% produce a composite of 110, not one the dear name dominates.
        out = composite([[Decimal(4000), Decimal(4400)], [Decimal(200), Decimal(220)]])
        assert out == pytest.approx([100.0, 110.0])

    def test_an_unpriceable_member_is_dropped_not_flat_lined(self) -> None:
        # Including it at a nominal 100 would mute the sector's real move.
        out = composite([[Decimal(0), Decimal(50)], [Decimal(100), Decimal(120)]])
        assert out == [100.0, 120.0]

    def test_truncates_to_the_shortest_member(self) -> None:
        out = composite([[Decimal(100), Decimal(110), Decimal(120)], [Decimal(100), Decimal(110)]])
        assert out == pytest.approx([100.0, 110.0])

    def test_nothing_priceable_is_empty_not_zero(self) -> None:
        assert composite([[], [Decimal(0)]]) == []


class TestRotation:
    """The assembled pipeline."""

    def test_a_sector_pulling_away_faster_and_faster_leads(self) -> None:
        periods = 60
        # Accelerating, not linear. A constant-rate gain is momentum-neutral
        # (see the test below), so a linear series would be testing the
        # boundary rule rather than the leading quadrant.
        sector = [Decimal(100) + Decimal(n * n) / Decimal(50) for n in range(periods)]
        benchmark = [Decimal(100)] * periods

        tail = rotation(sector, benchmark, stamps(periods))

        assert tail, "a strengthening sector should produce a tail"
        assert tail[-1].rs_ratio > 100.0
        assert tail[-1].rs_momentum > 100.0
        assert tail[-1].quadrant is Quadrant.LEADING

    def test_a_sector_losing_ground_faster_and_faster_lags(self) -> None:
        periods = 60
        sector = [Decimal(100) - Decimal(n * n) / Decimal(50) for n in range(periods)]
        benchmark = [Decimal(100)] * periods

        tail = rotation(sector, benchmark, stamps(periods))

        assert tail
        assert tail[-1].rs_ratio < 100.0
        assert tail[-1].rs_momentum < 100.0
        assert tail[-1].quadrant is Quadrant.LAGGING

    def test_a_constant_rate_decline_is_momentum_neutral(self) -> None:
        # Worth pinning rather than discovering again later. RS-Momentum is the
        # rate of change of RS-Ratio, and a *linear* price trend normalises to
        # a flat RS-Ratio: every window has the same shape, so the last point's
        # z-score is identical every period. The sector is weak (ratio below
        # 100) but it is not getting weaker at a changing rate, so momentum is
        # exactly neutral — which the cross rule then reads as improving.
        periods = 60
        sector = [Decimal(100) - Decimal(n) * Decimal("0.5") for n in range(periods)]
        benchmark = [Decimal(100)] * periods

        tail = rotation(sector, benchmark, stamps(periods))

        assert tail
        assert tail[-1].rs_ratio < 100.0
        assert tail[-1].rs_momentum == pytest.approx(100.0)

    def test_stamps_align_from_the_right(self) -> None:
        # Every stage of the pipeline is trailing, so the last point must carry
        # the last stamp. Aligning from the left would label every tail with
        # the time of a point drawn somewhere else.
        periods = 60
        all_stamps = stamps(periods)
        tail = rotation(
            [Decimal(100) + Decimal(n) for n in range(periods)],
            [Decimal(100)] * periods,
            all_stamps,
        )

        assert tail[-1].at == all_stamps[-1]

    def test_the_tail_is_capped_to_what_was_asked_for(self) -> None:
        periods = 80
        tail = rotation(
            [Decimal(100) + Decimal(n) for n in range(periods)],
            [Decimal(100)] * periods,
            stamps(periods),
            tail=5,
        )
        assert len(tail) == 5

    def test_points_are_ordered_oldest_first(self) -> None:
        periods = 60
        tail = rotation(
            [Decimal(100) + Decimal(n) for n in range(periods)],
            [Decimal(100)] * periods,
            stamps(periods),
        )
        assert [point.at for point in tail] == sorted(point.at for point in tail)

    def test_a_shallow_archive_returns_no_tail_rather_than_a_wrong_one(self) -> None:
        # Four sessions of daily closes cannot fill a fourteen-period window.
        # Empty is the honest answer; a two-point tail measured over a partial
        # window is a different statistic wearing the same axis labels.
        assert rotation([Decimal(100)] * 4, [Decimal(100)] * 4, stamps(4)) == ()

    def test_a_flat_pair_sits_at_the_cross(self) -> None:
        periods = 60
        tail = rotation([Decimal(100)] * periods, [Decimal(100)] * periods, stamps(periods))
        assert tail
        assert all(point.rs_ratio == pytest.approx(100.0) for point in tail)
        assert all(point.rs_momentum == pytest.approx(100.0) for point in tail)
