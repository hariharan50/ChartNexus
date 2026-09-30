"""Reference levels, against hand-worked arithmetic.

Pivots are the kind of formula that looks right in every code review and is
still wrong, so the cases here check the numbers rather than the shape: a
worked example, the ordering invariant that no valid session may break, and the
off-by-one that would quote levels from a session that has not finished.
"""

from __future__ import annotations

import pytest

from marketcompass.shared_kernel.domain.levels import (
    Bar,
    LevelOrigin,
    LevelSide,
    build_level,
    central_pivot_range,
    classic_pivots,
    cluster,
    distance,
    nearest,
    period_range,
    prior_session,
    side_of,
)

pytestmark = pytest.mark.unit


def bar(high: float, low: float, close: float, open_: float = 0.0) -> Bar:
    return Bar(open=open_ or close, high=high, low=low, close=close)


class TestClassicPivots:
    def test_the_worked_example(self) -> None:
        """H 25,620 / L 25,210 / C 25,386 → pivot 25,405.33.

        Every other level hangs off that mean, so if it is right and the span
        is right, the set is right.
        """
        pivots = classic_pivots(25620, 25210, 25386)

        assert pivots is not None
        assert pivots.pivot == pytest.approx(25405.333, abs=0.01)
        assert pivots.r1 == pytest.approx(25600.667, abs=0.01)
        assert pivots.s1 == pytest.approx(25190.667, abs=0.01)
        assert pivots.r2 == pytest.approx(25815.333, abs=0.01)
        assert pivots.s2 == pytest.approx(24995.333, abs=0.01)

    def test_the_levels_are_always_ordered(self) -> None:
        """S3 < S2 < S1 < P < R1 < R2 < R3, for any valid session.

        A sign slip anywhere in the set breaks this and nothing else, which is
        why it is asserted rather than assumed.
        """
        for high, low, close in [
            (25620, 25210, 25386),
            (25620, 25210, 25620),  # closed on the high
            (25620, 25210, 25210),  # closed on the low
            (100.5, 99.5, 100.0),  # a tight range
        ]:
            pivots = classic_pivots(high, low, close)
            assert pivots is not None, (high, low, close)
            levels = [
                pivots.s3,
                pivots.s2,
                pivots.s1,
                pivots.pivot,
                pivots.r1,
                pivots.r2,
                pivots.r3,
            ]
            assert levels == sorted(levels), (high, low, close, levels)

    @pytest.mark.parametrize(
        ("high", "low", "close"),
        [(25210, 25620, 25400), (0, 0, 0), (-5, -10, -7)],
    )
    def test_a_degenerate_session_yields_nothing(
        self, high: float, low: float, close: float
    ) -> None:
        """Inverted or non-positive bars are bad data, and pivots derived from
        them would be confidently meaningless."""
        assert classic_pivots(high, low, close) is None


class TestCentralPivotRange:
    def test_the_band_brackets_the_pivot_either_way_round(self) -> None:
        """TC and BC swap depending on where the close sits, so the dataclass
        normalises them — bottom is always the lower of the two."""
        narrow = central_pivot_range(25620, 25210, 25386)
        assert narrow is not None
        assert narrow.bottom <= narrow.top

        inverted_close = central_pivot_range(25620, 25210, 25250)
        assert inverted_close is not None
        assert inverted_close.bottom <= inverted_close.top

    def test_width_is_relative_so_it_compares_across_instruments(self) -> None:
        """A 40-point CPR is wide on NIFTY and narrow on SENSEX; the percentage
        is the number that transfers."""
        cpr = central_pivot_range(25620, 25210, 25386)

        assert cpr is not None
        assert cpr.width_percent == pytest.approx(
            (cpr.top - cpr.bottom) / cpr.pivot * 100, abs=1e-9
        )


class TestPriorSession:
    def test_it_takes_the_completed_bar_not_today_s(self) -> None:
        """The single easiest way to make a pre-market page lie is to quote
        "yesterday's high" off a bar that is still forming."""
        bars = [bar(100, 90, 95), bar(110, 100, 105), bar(120, 110, 115)]

        previous = prior_session(bars)

        assert previous is not None
        assert previous.high == 110

    def test_one_bar_is_not_enough(self) -> None:
        assert prior_session([bar(100, 90, 95)]) is None
        assert prior_session([]) is None


class TestPeriodRange:
    def test_the_window_excludes_the_forming_bar(self) -> None:
        """Today's spike must not become "the weekly high" before the session
        has closed."""
        bars = [bar(100, 90, 95), bar(110, 100, 105), bar(999, 110, 115)]

        window = period_range(bars, sessions=5)

        assert window is not None
        assert window.high == 110
        assert window.low == 90

    def test_it_reports_how_many_bars_it_actually_had(self) -> None:
        """A 52-week high computed from eleven bars is not one, and the caller
        needs to be able to say which it has."""
        bars = [bar(100 + i, 90 + i, 95 + i) for i in range(12)]

        window = period_range(bars, sessions=252)

        assert window is not None
        assert window.bars == 11

    def test_too_little_history_yields_nothing(self) -> None:
        assert period_range([bar(100, 90, 95)], sessions=5) is None


class TestDistance:
    def test_it_is_signed_toward_the_level(self) -> None:
        above = distance(25000, 25100)
        below = distance(25000, 24900)

        assert above.points == 100
        assert below.points == -100

    def test_the_atr_multiple_is_none_rather_than_zero_when_unknown(self) -> None:
        """0.0 would read as "right here" rather than "not known"."""
        assert distance(25000, 25100).atr_multiple is None
        assert distance(25000, 25100, atr=200).atr_multiple == pytest.approx(0.5)


class TestSideAndNearest:
    def test_a_level_within_tolerance_reads_as_at(self) -> None:
        assert side_of(25000, 25002, tolerance=5) is LevelSide.AT
        assert side_of(25000, 25100) is LevelSide.ABOVE
        assert side_of(25000, 24900) is LevelSide.BELOW

    def test_nearest_returns_the_closest_each_way(self) -> None:
        spot = 25000
        levels = [
            build_level("S1", 24900, LevelOrigin.PIVOT, spot=spot),
            build_level("S2", 24800, LevelOrigin.PIVOT, spot=spot),
            build_level("R1", 25100, LevelOrigin.PIVOT, spot=spot),
            build_level("R2", 25200, LevelOrigin.PIVOT, spot=spot),
        ]

        below, above = nearest(levels)

        assert below is not None and below.label == "S1"
        assert above is not None and above.label == "R1"

    def test_price_outside_the_map_yields_none_rather_than_the_furthest_level(
        self,
    ) -> None:
        """Being above every level is itself the reading; substituting the
        highest one would hide a breakout."""
        spot = 26000
        levels = [build_level("R1", 25100, LevelOrigin.PIVOT, spot=spot)]

        below, above = nearest(levels)

        assert below is not None
        assert above is None


class TestCluster:
    def test_levels_from_different_methods_that_agree_form_a_cluster(self) -> None:
        spot = 25000
        levels = [
            build_level("R1", 25600, LevelOrigin.PIVOT, spot=spot),
            build_level("Call wall", 25610, LevelOrigin.OPTION_WALL, spot=spot),
            build_level("PDH", 25618, LevelOrigin.PRIOR_DAY, spot=spot),
        ]

        clusters = cluster(levels, tolerance=25)

        assert len(clusters) == 1
        assert len(clusters[0].members) == 3
        assert set(clusters[0].origins) == {
            LevelOrigin.PIVOT,
            LevelOrigin.OPTION_WALL,
            LevelOrigin.PRIOR_DAY,
        }

    def test_two_levels_from_the_same_method_are_not_a_confluence(self) -> None:
        """Two pivots landing close together is an artefact of one formula.
        Presenting it as agreement manufactures significance out of arithmetic.
        """
        spot = 25000
        levels = [
            build_level("R1", 25600, LevelOrigin.PIVOT, spot=spot),
            build_level("R2", 25605, LevelOrigin.PIVOT, spot=spot),
        ]

        assert cluster(levels, tolerance=25) == ()

    def test_levels_further_apart_than_the_tolerance_stay_separate(self) -> None:
        spot = 25000
        levels = [
            build_level("R1", 25600, LevelOrigin.PIVOT, spot=spot),
            build_level("Call wall", 25900, LevelOrigin.OPTION_WALL, spot=spot),
        ]

        assert cluster(levels, tolerance=25) == ()

    def test_a_non_positive_tolerance_clusters_nothing(self) -> None:
        spot = 25000
        levels = [
            build_level("R1", 25600, LevelOrigin.PIVOT, spot=spot),
            build_level("Call wall", 25600, LevelOrigin.OPTION_WALL, spot=spot),
        ]

        assert cluster(levels, tolerance=0) == ()
