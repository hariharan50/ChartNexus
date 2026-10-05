"""The pre-market inference, as pure maths.

The cases here are the ones that would be silently wrong rather than obviously
broken: a gap bucketed against the wrong yardstick, a score that looks confident
on three inputs, an expected move blended out of three incompatible measures,
and a level ladder that quotes yesterday off a bar that has not closed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from chartnexus.contexts.pre_market.domain import compose, expected_move, gap
from chartnexus.contexts.pre_market.domain.gap import GapBasis, GapBucket
from chartnexus.contexts.pre_market.domain.readings import (
    BY_SYMBOL,
    BreadthReading,
    CandleSeries,
    GlobalReading,
    OptionsReading,
    Sources,
    SpotReading,
)
from chartnexus.contexts.pre_market.domain.regime import (
    Axis,
    RegimeBand,
    Stance,
    band_of,
    compose as compose_regime,
    factor,
)
from chartnexus.shared_kernel.domain.levels import Bar, LevelOrigin

pytestmark = pytest.mark.unit


def series(count: int = 260, *, start: float = 25_000, step: float = 10) -> CandleSeries:
    """A rising daily series long enough for every indicator to resolve."""
    bars = []
    for index in range(count):
        close = start + index * step
        bars.append(Bar(open=close - step / 2, high=close + 40, low=close - 40, close=close))
    return CandleSeries(symbol="NIFTY", bars=tuple(bars))


def options(**overrides: object) -> OptionsReading:
    base: dict[str, object] = {
        "expiry": None,
        "days_to_expiry": 3,
        "spot": Decimal("25000"),
        "atm_strike": Decimal("25000"),
        "pcr_oi": Decimal("1.18"),
        "pcr_change": Decimal("0.04"),
        "total_call_oi": 48_200_000,
        "total_put_oi": 56_900_000,
        "max_pain": Decimal("25050"),
        "call_wall": Decimal("25700"),
        "put_wall": Decimal("24300"),
        "gamma_flip": Decimal("25100"),
        "atm_iv": Decimal("13.8"),
        "iv_percentile": Decimal("38"),
        "atm_straddle": Decimal("185"),
        "india_vix": Decimal("13.82"),
        "india_vix_change_percent": Decimal("-4.21"),
    }
    base.update(overrides)
    return OptionsReading(**base)  # type: ignore[arg-type]


class TestGap:
    def test_the_bucket_is_measured_against_atr_not_a_fixed_percent(self) -> None:
        """The same 60-point gap is a shrug on a wide-range index and an event
        on a quiet one. A fixed band would file both identically and quietly
        average two market regimes into every statistic downstream.
        """
        quiet = gap.measure(Decimal("25060"), Decimal("25000"), atr=80)
        wide = gap.measure(Decimal("25060"), Decimal("25000"), atr=400)

        assert quiet is not None and wide is not None
        assert quiet.bucket is GapBucket.UP
        assert wide.bucket is GapBucket.FLAT
        assert quiet.basis is GapBasis.ATR

    def test_it_falls_back_to_percent_and_says_so(self) -> None:
        without_atr = gap.measure(Decimal("25060"), Decimal("25000"))

        assert without_atr is not None
        assert without_atr.basis is GapBasis.PERCENT
        assert without_atr.atr_multiple is None

    def test_a_missing_open_yields_nothing_rather_than_a_derived_one(self) -> None:
        """Before the bell there is no open. Substituting the GIFT-implied
        level would put a quote in the slot reserved for a print."""
        assert gap.measure(None, Decimal("25000"), atr=200) is None
        assert gap.measure(Decimal("25060"), None) is None
        assert gap.measure(Decimal("25060"), Decimal("0")) is None

    def test_agreement_names_a_divergence_rather_than_averaging_it(self) -> None:
        actual_up = gap.measure(Decimal("25200"), Decimal("25000"), atr=100)
        quoted_up = gap.implied(Decimal("25180"), Decimal("25000"), atr=100)
        quoted_down = gap.implied(Decimal("24800"), Decimal("25000"), atr=100)

        assert gap.agreement(actual_up, quoted_up) == "aligned"
        assert gap.agreement(actual_up, quoted_down) == "diverged"

    def test_agreement_is_inconclusive_when_either_leg_is_flat(self) -> None:
        flat = gap.measure(Decimal("25001"), Decimal("25000"), atr=200)
        up = gap.implied(Decimal("25400"), Decimal("25000"), atr=200)

        assert gap.agreement(flat, up) == "inconclusive"
        assert gap.agreement(None, up) is None


class TestExpectedMove:
    def test_the_three_measures_are_reported_side_by_side_never_blended(self) -> None:
        """They answer different questions over different horizons. A blend is
        neither what the market charges nor what the index does.
        """
        move = expected_move.reconcile(
            Decimal("25000"),
            straddle_price=Decimal("185"),
            india_vix=Decimal("13.82"),
            atr=200,
            days_to_expiry=3,
        )

        assert move is not None
        assert move.straddle is not None
        assert move.vix is not None
        assert move.atr is not None
        assert move.straddle.points != move.vix.points != move.atr.points

    def test_each_measure_brackets_the_spot(self) -> None:
        move = expected_move.reconcile(Decimal("25000"), atr=200)

        assert move is not None and move.atr is not None
        assert move.atr.lower == pytest.approx(24800)
        assert move.atr.upper == pytest.approx(25200)

    def test_an_event_premium_is_named(self) -> None:
        """Options charging far more than the index has been travelling is the
        informative case, and it is exactly what a blend would erase."""
        move = expected_move.reconcile(
            Decimal("25000"), straddle_price=Decimal("500"), atr=100, days_to_expiry=1
        )

        assert move is not None
        assert move.note is not None
        assert "wider move" in move.note

    def test_measures_that_agree_say_nothing(self) -> None:
        move = expected_move.reconcile(
            Decimal("25000"), straddle_price=Decimal("250"), atr=200, days_to_expiry=1
        )

        assert move is not None
        assert move.note is None

    def test_missing_inputs_drop_their_own_measure_only(self) -> None:
        move = expected_move.reconcile(Decimal("25000"), atr=200)

        assert move is not None
        assert move.straddle is None
        assert move.vix is None
        assert move.atr is not None


class TestRegime:
    def test_the_composite_decomposes_back_into_its_factors(self) -> None:
        """A score whose inputs cannot be inspected is a horoscope with a
        decimal point."""
        result = compose_regime(
            (
                factor("a", "A", Axis.TREND, points=12.0, reading="20 > 50"),
                factor("b", "B", Axis.BREADTH, points=-4.0, reading="800 up / 1200 down"),
            ),
            expected=9,
        )

        assert result.score == pytest.approx(58.0)
        assert sum(item.points for item in result.factors) == pytest.approx(8.0)
        assert all(item.reading for item in result.factors)

    def test_factors_are_ordered_loudest_first(self) -> None:
        result = compose_regime(
            (
                factor("small", "Small", Axis.TREND, points=1.0, reading="x"),
                factor("big", "Big", Axis.GLOBAL, points=-20.0, reading="y"),
            ),
            expected=9,
        )

        assert result.factors[0].key == "big"

    def test_confidence_comes_from_coverage_not_from_conviction(self) -> None:
        """A lopsided score off two inputs is a thin reading, not a confident
        one, and the two must not look alike."""
        lopsided = compose_regime(
            (factor("a", "A", Axis.TREND, points=45.0, reading="x"),), expected=9
        )
        broad = compose_regime(
            tuple(factor(f"f{n}", "F", Axis.TREND, points=1.0, reading="x") for n in range(8)),
            expected=9,
        )

        assert lopsided.score > broad.score
        assert lopsided.confidence == "thin"
        assert broad.confidence == "high"

    def test_no_inputs_reads_as_no_opinion_rather_than_bearish(self) -> None:
        empty = compose_regime((), expected=9)

        assert empty.score == pytest.approx(50.0)
        assert empty.band is RegimeBand.NEUTRAL
        assert empty.inputs_present == 0

    def test_the_score_cannot_leave_its_range(self) -> None:
        runaway = compose_regime(
            (factor("a", "A", Axis.TREND, points=999.0, reading="x"),), expected=9
        )
        collapse = compose_regime(
            (factor("a", "A", Axis.TREND, points=-999.0, reading="x"),), expected=9
        )

        assert runaway.score == 100.0
        assert collapse.score == 0.0

    def test_an_axis_with_no_factors_is_neutral_not_absent(self) -> None:
        result = compose_regime(
            (factor("a", "A", Axis.TREND, points=5.0, reading="x"),), expected=9
        )
        axes = {axis.axis: axis for axis in result.axes}

        assert len(result.axes) == len(Axis)
        assert axes[Axis.BREADTH].stance is Stance.NEUTRAL
        assert axes[Axis.BREADTH].resolved is False

    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (10, RegimeBand.STRONGLY_BEARISH),
            (35, RegimeBand.BEARISH),
            (50, RegimeBand.NEUTRAL),
            (65, RegimeBand.BULLISH),
            (90, RegimeBand.STRONGLY_BULLISH),
        ],
    )
    def test_bands(self, score: float, expected: RegimeBand) -> None:
        assert band_of(score) is expected


class TestTechnicals:
    def test_a_rising_series_stacks_up(self) -> None:
        read = compose.technicals_of(series())

        assert read is not None
        assert read.ema_stacked_up is True
        assert read.atr14 is not None
        assert read.atr_percent is not None

    def test_a_mixed_stack_is_none_not_a_direction(self) -> None:
        """ "The moving averages disagree" is a real state, and collapsing it
        either way would report a trend the chart does not have.

        A long uptrend followed by a sharp selloff: the fast EMAs have rolled
        over while the slow ones are still rising, which is precisely the
        moment a trend read is least entitled to pick a side.
        """
        rising = series(count=240).bars
        last = rising[-1].close
        falling = tuple(
            Bar(
                open=last - n * 60,
                high=last - n * 60 + 40,
                low=last - n * 60 - 40,
                close=last - (n + 1) * 60,
            )
            for n in range(20)
        )
        read = compose.technicals_of(CandleSeries(symbol="NIFTY", bars=rising + falling))

        assert read is not None
        assert read.ema20 is not None and read.ema200 is not None
        assert read.ema20 < read.ema50 if read.ema50 else True
        assert read.ema_stacked_up is None

    def test_a_thin_history_leaves_the_long_emas_empty(self) -> None:
        read = compose.technicals_of(series(count=30))

        assert read is not None
        assert read.ema20 is not None
        assert read.ema200 is None

    def test_no_series_yields_nothing(self) -> None:
        assert compose.technicals_of(None) is None


class TestLevelMap:
    def test_the_ladder_merges_every_method_and_orders_it(self) -> None:
        book = series()
        result = compose.level_map_of(Decimal("27590"), book, options(), atr=80)

        assert result is not None
        prices = [level.price for level in result.levels]
        assert prices == sorted(prices, reverse=True)
        origins = {level.origin for level in result.levels}
        assert LevelOrigin.PIVOT in origins
        assert LevelOrigin.OPTION_WALL in origins
        assert LevelOrigin.PRIOR_DAY in origins

    def test_prior_day_comes_from_the_completed_bar(self) -> None:
        """Quoting "yesterday's high" off a bar still forming is the single
        easiest way to make a pre-market page lie."""
        book = series(count=5)
        result = compose.level_map_of(Decimal("25040"), book, None, atr=50)

        assert result is not None
        assert result.prior_day_close == book.bars[-2].close

    def test_nearest_levels_bracket_the_spot(self) -> None:
        result = compose.level_map_of(Decimal("27590"), series(), options(), atr=80)

        assert result is not None
        if result.nearest_below is not None:
            assert result.nearest_below.price < result.spot
        if result.nearest_above is not None:
            assert result.nearest_above.price > result.spot

    def test_no_candles_means_no_map_rather_than_an_empty_ladder(self) -> None:
        assert compose.level_map_of(Decimal("25000"), None, options(), atr=80) is None
        assert (
            compose.level_map_of(Decimal("25000"), CandleSeries(symbol="NIFTY", bars=()), None)
            is None
        )


class TestVolatility:
    def test_a_thin_vix_history_reports_the_count_and_no_percentile(self) -> None:
        """The reader still needs to know *why* the rank is empty."""
        read = compose.volatility_of(options(), vix_history=(12.0, 13.0, 14.0))

        assert read is not None
        assert read.vix_percentile is None
        assert read.vix_sample_sessions == 3

    def test_a_full_history_ranks(self) -> None:
        history = tuple(float(n) for n in range(10, 40))
        read = compose.volatility_of(options(), vix_history=history)

        assert read is not None
        assert read.vix_percentile is not None


class TestRegimeAssembly:
    def test_every_missing_upstream_lowers_coverage_rather_than_the_score(self) -> None:
        technicals = compose.technicals_of(series())
        full = compose.regime_of(
            technicals,
            options(),
            GlobalReading(pressure_score=Decimal("30"), pressure_band="up"),
            BreadthReading(advances=1400, declines=800, unchanged=50, priced=50, universe=50),
            gap=gap.measure(Decimal("25060"), Decimal("25000"), atr=80),
        )
        bare = compose.regime_of(technicals, None, None, None, gap=None)

        assert full.inputs_present > bare.inputs_present
        assert full.confidence == "high"
        assert bare.confidence in {"thin", "moderate"}

    def test_it_never_raises_on_an_entirely_empty_board(self) -> None:
        result = compose.regime_of(None, None, None, None, gap=None)

        assert result.score == pytest.approx(50.0)
        assert result.inputs_present == 0


class TestHeadline:
    def test_only_nifty_gets_an_implied_gap(self) -> None:
        """BANK NIFTY and SENSEX have no overnight contract; borrowing NIFTY's
        would invent a number the market never quoted."""
        spot = SpotReading(
            symbol="BANKNIFTY",
            label="BANK NIFTY",
            price=Decimal("57000"),
            previous_close=Decimal("56900"),
            day_open=Decimal("56950"),
            change=Decimal("100"),
            change_percent=Decimal("0.18"),
            source="live",
        )

        card = compose.headline_card(BY_SYMBOL["BANKNIFTY"], spot, atr=300)

        assert card.gap is not None
        assert card.implied_gap is None

    def test_sensex_is_flagged_as_untracked_for_breadth(self) -> None:
        """No constituent weight table exists for it, and an empty breadth
        panel on a headline index reads as a bug."""
        assert BY_SYMBOL["SENSEX"].breadth_tracked is False
        assert BY_SYMBOL["NIFTY"].breadth_tracked is True

    def test_a_missing_quote_still_produces_a_card(self) -> None:
        card = compose.headline_card(BY_SYMBOL["NIFTY"], None)

        assert card.price is None
        assert card.source == "mock"


class TestSources:
    def test_the_page_is_only_as_live_as_its_weakest_leg(self) -> None:
        assert Sources(parts={"spot": "live", "chain": "mock"}).weakest() == "mock"
        assert Sources(parts={"spot": "live", "chain": "cached"}).weakest() == "cached"
        assert Sources(parts={"spot": "live"}).weakest() == "live"

    def test_nothing_answered_is_not_live(self) -> None:
        assert Sources().weakest() == "mock"
