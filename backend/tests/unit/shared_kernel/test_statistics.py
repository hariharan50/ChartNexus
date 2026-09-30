"""Descriptive statistics, and the two "percentiles" that are not the same.

The cases that matter here are the refusals. Every function returns ``None``
rather than a flattering number on a thin sample, because these feed a screener
where a percentile is read as a fact.
"""

from __future__ import annotations

import pytest

from marketcompass.shared_kernel.domain.statistics import (
    MIN_SAMPLE,
    bucket,
    mean,
    median,
    percentile_rank,
    rank_in_range,
    share,
    stdev,
)

pytestmark = pytest.mark.unit

#: 0..99, so a value's percentile is legible by inspection.
HISTORY = [float(n) for n in range(100)]


class TestPercentileRank:
    def test_it_counts_observations_at_or_below(self) -> None:
        assert percentile_rank(HISTORY, 49) == pytest.approx(50.0)
        assert percentile_rank(HISTORY, 0) == pytest.approx(1.0)
        assert percentile_rank(HISTORY, 99) == pytest.approx(100.0)

    def test_a_value_beyond_the_sample_saturates_rather_than_extrapolating(self) -> None:
        assert percentile_rank(HISTORY, 1_000) == pytest.approx(100.0)
        assert percentile_rank(HISTORY, -1_000) == pytest.approx(0.0)

    def test_a_thin_sample_refuses(self) -> None:
        assert percentile_rank([1.0, 2.0, 3.0], 2) is None
        assert percentile_rank(HISTORY[: MIN_SAMPLE - 1], 5) is None
        assert percentile_rank(HISTORY[:MIN_SAMPLE], 5) is not None

    def test_the_floor_can_be_lowered_deliberately(self) -> None:
        """A caller willing to show a reading off four observations has to say
        so — and then owes the reader the sample size on screen."""
        assert percentile_rank([1.0, 2.0, 3.0, 4.0], 2, minimum=4) == pytest.approx(50.0)


class TestRankInRange:
    def test_it_is_pure_min_max_not_a_count(self) -> None:
        assert rank_in_range(HISTORY, 49.5) == pytest.approx(50.0)

    def test_it_disagrees_with_percentile_rank_on_a_skewed_sample(self) -> None:
        """The reason both exist. Ninety-nine readings near zero and one spike:
        the value sits high by *count* and low by *range*, and calling either
        one "the percentile" misleads.
        """
        skewed = [1.0] * 99 + [1_000.0]

        by_count = percentile_rank(skewed, 1.0)
        by_range = rank_in_range(skewed, 1.0)

        assert by_count is not None and by_range is not None
        assert by_count == pytest.approx(99.0)
        assert by_range == pytest.approx(0.0)

    def test_a_flat_history_has_no_band_to_rank_within(self) -> None:
        assert rank_in_range([5.0] * 50, 5.0) is None

    def test_a_thin_sample_refuses(self) -> None:
        assert rank_in_range([1.0, 9.0], 5) is None


class TestAverages:
    def test_median_resists_the_one_crash_session_a_mean_does_not(self) -> None:
        """Conditional outcome stats are exactly where this matters: one
        gap-and-crash day drags the mean off the typical session."""
        outcomes = [0.2, 0.3, 0.4, 0.5, -9.0]

        assert median(outcomes) == pytest.approx(0.3)
        assert mean(outcomes) == pytest.approx(-1.52)

    def test_median_of_an_even_sample_averages_the_middle_pair(self) -> None:
        assert median([1.0, 2.0, 3.0, 4.0]) == pytest.approx(2.5)

    def test_empty_samples_yield_nothing(self) -> None:
        assert mean([]) is None
        assert median([]) is None
        assert stdev([1.0]) is None

    def test_stdev_is_bessel_corrected(self) -> None:
        assert stdev([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]) == pytest.approx(
            2.13809, abs=1e-5
        )


class TestShare:
    def test_it_refuses_an_empty_universe_rather_than_dividing_by_zero(self) -> None:
        """The morning the constituent board comes back empty must not take the
        page down, and must not print 0%."""
        assert share(0, 0) is None
        assert share(5, 0) is None
        assert share(9, 12) == pytest.approx(75.0)


class TestBucket:
    def test_edges_are_exclusive_upper_bounds_in_ascending_order(self) -> None:
        edges = [-1.0, -0.3, 0.3, 1.0]
        labels = ["down_large", "down", "flat", "up", "up_large"]

        assert bucket(-2.0, edges, labels) == "down_large"
        assert bucket(-0.5, edges, labels) == "down"
        assert bucket(0.0, edges, labels) == "flat"
        assert bucket(0.5, edges, labels) == "up"
        assert bucket(2.0, edges, labels) == "up_large"

    def test_a_value_on_an_edge_falls_into_the_upper_bucket(self) -> None:
        assert bucket(0.3, [-0.3, 0.3], ["down", "flat", "up"]) == "up"

    def test_a_mismatched_vocabulary_is_rejected_loudly(self) -> None:
        """Silently mis-bucketing would poison every conditional statistic
        downstream, and it would never look wrong."""
        with pytest.raises(ValueError, match="one more label than edges"):
            bucket(0.0, [0.0], ["only_one"])
