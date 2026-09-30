"""Readings in, view out. The whole inference, as pure functions.

Everything the page concludes happens here, with no I/O anywhere in reach. That
is what makes the page's claims testable: a fixture of readings produces one
view, deterministically, and the interesting cases — a missing option chain, a
thin candle history, an index with no constituent table — are ordinary unit
tests rather than things you find out about in production at 09:10.

The application layer's only job is to fetch the readings and hand them here.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from itertools import pairwise

from marketcompass.contexts.pre_market.domain import (
    expected_move as em,
    gap as gap_math,
    regime as regime_math,
)
from marketcompass.contexts.pre_market.domain.readings import (
    BreadthReading,
    CandleSeries,
    GlobalReading,
    IndexDefinition,
    OptionsReading,
    SpotReading,
)
from marketcompass.contexts.pre_market.domain.regime import Axis, Factor
from marketcompass.contexts.pre_market.domain.view import (
    HeadlineIndex,
    LevelMap,
    Technicals,
    Volatility,
)
from marketcompass.shared_kernel.domain import indicators
from marketcompass.shared_kernel.domain.levels import (
    Level,
    LevelOrigin,
    build_level,
    central_pivot_range,
    classic_pivots,
    cluster,
    nearest,
    period_range,
    prior_session,
)
from marketcompass.shared_kernel.domain.statistics import percentile_rank

#: Sessions in a trading week and a trading month. Approximations, and the
#: ranges they produce are labelled "last 5 sessions" rather than "this week"
#: for exactly that reason.
_WEEK_SESSIONS = 5
_MONTH_SESSIONS = 21
_YEAR_SESSIONS = 252

#: Confluence tolerance as a fraction of ATR. A fifth of a day's range is close
#: enough that two levels are, in practice, one zone.
_CLUSTER_ATR_FRACTION = 0.2

#: How many factors the scorecard tries to build. Held here so ``coverage``
#: reports honestly when upstreams are missing.
_EXPECTED_FACTORS = 9

#: Two EMAs is the fewest that can be called a stack at all.
_MIN_STACK = 2
#: ADX convention: below 20 the market is ranging, not trending.
_TRENDING_ADX = 20.0


# -- headline -----------------------------------------------------------------


def headline_card(
    index: IndexDefinition,
    spot: SpotReading | None,
    *,
    atr: float | None = None,
    gift_level: Decimal | None = None,
) -> HeadlineIndex:
    """One index card, with its realised and quoted gaps kept apart.

    ``gift_level`` is only passed for NIFTY: BANK NIFTY and SENSEX have no
    overnight contract, and borrowing NIFTY's to imply their open would invent
    a number the market never quoted.
    """
    if spot is None:
        return HeadlineIndex(
            symbol=index.symbol,
            label=index.label,
            price=None,
            change=None,
            change_percent=None,
            previous_close=None,
            gap=None,
            implied_gap=None,
            breadth_tracked=index.breadth_tracked,
            source="mock",
        )

    return HeadlineIndex(
        symbol=index.symbol,
        label=index.label,
        price=spot.price,
        change=spot.change,
        change_percent=spot.change_percent,
        previous_close=spot.previous_close,
        gap=gap_math.measure(spot.day_open, spot.previous_close, atr=atr),
        implied_gap=gap_math.implied(gift_level, spot.previous_close, atr=atr),
        breadth_tracked=index.breadth_tracked,
        source=spot.source,
    )


# -- technicals ---------------------------------------------------------------


def technicals_of(series: CandleSeries | None) -> Technicals | None:
    """The focused index's own chart, read once.

    Every value is ``None`` when the history is too short for it — the shared
    kernel's contract — so a three-week-old instrument shows dashes rather than
    a 200-EMA computed from forty bars.
    """
    if series is None or not series.bars:
        return None

    closes = list(series.closes)
    highs = list(series.highs)
    lows = list(series.lows)

    ema20 = indicators.ema(closes, 20)
    ema50 = indicators.ema(closes, 50)
    ema100 = indicators.ema(closes, 100)
    ema200 = indicators.ema(closes, 200)
    atr14 = indicators.atr(highs, lows, closes, 14)
    last = closes[-1] if closes else None

    return Technicals(
        ema20=ema20,
        ema50=ema50,
        ema100=ema100,
        ema200=ema200,
        ema_stacked_up=_stack(ema20, ema50, ema100, ema200),
        rsi14=indicators.rsi(closes, 14),
        adx14=indicators.adx(highs, lows, closes, 14),
        atr14=atr14,
        atr_percent=(atr14 / last * 100) if atr14 and last else None,
        bollinger_width=indicators.bollinger_width(closes, 20),
        realized_vol20=indicators.realized_vol(closes, 20),
    )


def _stack(*emas: float | None) -> bool | None:
    """``True`` fully ascending, ``False`` fully descending, ``None`` mixed.

    ``None`` for a mixed stack is deliberate: "the moving averages disagree" is
    a real state, and collapsing it into either direction would report a trend
    the chart does not have.
    """
    values = [value for value in emas if value is not None]
    if len(values) < _MIN_STACK:
        return None
    if all(a > b for a, b in pairwise(values)):
        return True
    if all(a < b for a, b in pairwise(values)):
        return False
    return None


# -- levels -------------------------------------------------------------------


def level_map_of(
    spot: Decimal | None,
    series: CandleSeries | None,
    options: OptionsReading | None,
    *,
    atr: float | None = None,
) -> LevelMap | None:
    """Every reference price, merged into one ordered ladder.

    Pivots, prior-day extremes, period ranges and the option book's heavy
    strikes all land in one list because that is how they are traded — as a
    single map — and because confluence between *different* methods is the only
    thing on this panel that is more than one opinion.
    """
    if spot is None or spot <= 0 or series is None or not series.bars:
        return None

    price = float(spot)
    previous = prior_session(series.bars)
    pivots = (
        classic_pivots(previous.high, previous.low, previous.close) if previous else None
    )
    cpr = (
        central_pivot_range(previous.high, previous.low, previous.close)
        if previous
        else None
    )
    week = period_range(series.bars, sessions=_WEEK_SESSIONS)
    month = period_range(series.bars, sessions=_MONTH_SESSIONS)
    year = period_range(series.bars, sessions=_YEAR_SESSIONS)

    levels: list[Level] = []

    def add(label: str, value: float | None, origin: LevelOrigin) -> None:
        if value is not None and value > 0:
            levels.append(build_level(label, value, origin, spot=price, atr=atr))

    if pivots is not None:
        for label, value in (
            ("R3", pivots.r3),
            ("R2", pivots.r2),
            ("R1", pivots.r1),
            ("Pivot", pivots.pivot),
            ("S1", pivots.s1),
            ("S2", pivots.s2),
            ("S3", pivots.s3),
        ):
            add(label, value, LevelOrigin.PIVOT)
    if cpr is not None:
        add("CPR top", cpr.top, LevelOrigin.CENTRAL_PIVOT)
        add("CPR bottom", cpr.bottom, LevelOrigin.CENTRAL_PIVOT)
    if previous is not None:
        add("Prev day high", previous.high, LevelOrigin.PRIOR_DAY)
        add("Prev day low", previous.low, LevelOrigin.PRIOR_DAY)
        add("Prev day close", previous.close, LevelOrigin.PRIOR_DAY)
    if week is not None:
        add("5-session high", week.high, LevelOrigin.WEEKLY)
        add("5-session low", week.low, LevelOrigin.WEEKLY)
    if month is not None:
        add("21-session high", month.high, LevelOrigin.MONTHLY)
        add("21-session low", month.low, LevelOrigin.MONTHLY)
    if year is not None:
        add("52-week high", year.high, LevelOrigin.YEARLY)
        add("52-week low", year.low, LevelOrigin.YEARLY)
    if options is not None:
        add(
            "Call wall",
            float(options.call_wall) if options.call_wall else None,
            LevelOrigin.OPTION_WALL,
        )
        add(
            "Put wall",
            float(options.put_wall) if options.put_wall else None,
            LevelOrigin.OPTION_WALL,
        )
        add(
            "Max pain",
            float(options.max_pain) if options.max_pain else None,
            LevelOrigin.MAX_PAIN,
        )
        add(
            "Gamma flip",
            float(options.gamma_flip) if options.gamma_flip else None,
            LevelOrigin.GAMMA_FLIP,
        )

    tolerance = (atr or 0.0) * _CLUSTER_ATR_FRACTION
    clusters = cluster(levels, tolerance=tolerance)
    below, above = nearest(levels)

    return LevelMap(
        spot=price,
        pivots=pivots,
        central_pivot=cpr,
        prior_day_high=previous.high if previous else None,
        prior_day_low=previous.low if previous else None,
        prior_day_close=previous.close if previous else None,
        week=week,
        month=month,
        year=year,
        levels=tuple(sorted(levels, key=lambda item: item.price, reverse=True)),
        clusters=clusters,
        nearest_above=above,
        nearest_below=below,
    )


# -- volatility ---------------------------------------------------------------


def volatility_of(
    options: OptionsReading | None, vix_history: tuple[float, ...] = ()
) -> Volatility | None:
    """India VIX with its rank, and the chain's own ATM implied volatility.

    The sample size travels with the percentile, always. A VIX rank off eleven
    sessions is not a rank, and ``percentile_rank`` refuses it — but the reader
    still needs to know *why* the field is empty, which the count answers.
    """
    if options is None:
        return None

    vix = options.india_vix
    return Volatility(
        india_vix=vix,
        india_vix_change_percent=options.india_vix_change_percent,
        vix_percentile=(
            percentile_rank(vix_history, float(vix)) if vix is not None else None
        ),
        vix_sample_sessions=len(vix_history),
        atm_iv=options.atm_iv,
        iv_percentile=options.iv_percentile,
    )


# -- expected move ------------------------------------------------------------


def expected_move_of(
    spot: Decimal | None, options: OptionsReading | None, *, atr: float | None
) -> em.ExpectedMove | None:
    if spot is None:
        return None
    return em.reconcile(
        spot,
        straddle_price=options.atm_straddle if options else None,
        india_vix=options.india_vix if options else None,
        atr=atr,
        days_to_expiry=options.days_to_expiry if options else None,
    )


# -- regime -------------------------------------------------------------------


def regime_of(
    technicals: Technicals | None,
    options: OptionsReading | None,
    global_cues: GlobalReading | None,
    breadth: BreadthReading | None,
    *,
    gap: gap_math.Gap | None,
) -> regime_math.Regime:
    """Six axes from whatever answered, with the misses counted.

    Weights are judgement, not a fit. They are stated here in one place so the
    page can say so and a reader can argue with them.
    """
    factors: list[Factor] = []

    if technicals is not None:
        if technicals.ema_stacked_up is not None:
            factors.append(
                regime_math.factor(
                    "ema_stack",
                    "EMA stack",
                    Axis.TREND,
                    points=12.0 if technicals.ema_stacked_up else -12.0,
                    reading="20 > 50 > 100 > 200"
                    if technicals.ema_stacked_up
                    else "20 < 50 < 100 < 200",
                )
            )
        if technicals.adx14 is not None:
            trending = technicals.adx14 >= _TRENDING_ADX
            factors.append(
                regime_math.factor(
                    "adx",
                    "Trend strength",
                    Axis.TREND,
                    points=4.0 if trending else -2.0,
                    reading=f"ADX {technicals.adx14:.1f}",
                    note=None if trending else "Below 20 — range, not trend.",
                )
            )
        if technicals.rsi14 is not None:
            factors.append(
                regime_math.factor(
                    "rsi",
                    "Momentum",
                    Axis.MOMENTUM,
                    points=(technicals.rsi14 - 50) * 0.25,
                    reading=f"RSI {technicals.rsi14:.1f}",
                )
            )
        if technicals.atr_percent is not None:
            calm = technicals.atr_percent < 1.0
            factors.append(
                regime_math.factor(
                    "atr_percent",
                    "Realised range",
                    Axis.VOLATILITY,
                    points=3.0 if calm else -3.0,
                    reading=f"ATR {technicals.atr_percent:.2f}% of spot",
                )
            )

    if gap is not None:
        factors.append(
            regime_math.factor(
                "gap",
                "Opening gap",
                Axis.MOMENTUM,
                points=float(gap.percent) * 4,
                reading=f"{gap.percent:+.2f}% ({gap.bucket.value.replace('_', ' ')})",
            )
        )

    if options is not None:
        if options.pcr_oi is not None:
            # Above 1 means more puts written than calls — conventionally read
            # as support. Scaled gently: PCR is noisy and regularly wrong.
            factors.append(
                regime_math.factor(
                    "pcr",
                    "Put-call ratio",
                    Axis.DERIVATIVES,
                    points=float(options.pcr_oi - Decimal(1)) * 10,
                    reading=f"PCR {options.pcr_oi:.2f}",
                )
            )
        if options.india_vix is not None:
            elevated = options.india_vix >= Decimal(20)
            factors.append(
                regime_math.factor(
                    "vix",
                    "Volatility regime",
                    Axis.VOLATILITY,
                    points=-6.0 if elevated else 3.0,
                    reading=f"India VIX {options.india_vix:.2f}",
                )
            )

    if global_cues is not None and global_cues.pressure_score is not None:
        factors.append(
            regime_math.factor(
                "global_pressure",
                "Overnight pressure",
                Axis.GLOBAL,
                points=float(global_cues.pressure_score) * 0.12,
                reading=f"{global_cues.pressure_score:+.1f} composite",
                note="Weights are fixed and unfitted — an illustrative read.",
            )
        )

    if (
        breadth is not None
        and breadth.advances is not None
        and breadth.declines is not None
        and (breadth.advances + breadth.declines) > 0
    ):
        total = breadth.advances + breadth.declines
        net = (breadth.advances - breadth.declines) / total
        factors.append(
            regime_math.factor(
                "advance_decline",
                "Participation",
                Axis.BREADTH,
                points=net * 10,
                reading=f"{breadth.advances} up / {breadth.declines} down",
            )
        )

    return regime_math.compose(tuple(factors), expected=_EXPECTED_FACTORS)


# -- assembly helper ----------------------------------------------------------


def atr_of(technicals: Technicals | None) -> float | None:
    """The ATR the gap bucket, level distances and cluster tolerance all use.

    Pulled out so every one of them uses the same number. Three call sites
    each deriving their own would be three chances to use a different period.
    """
    return technicals.atr14 if technicals else None


def as_of_from(*candidates: datetime | None) -> datetime | None:
    """The earliest reading time among the legs that answered.

    Earliest, not latest: the page is only as current as its stalest input, and
    stamping it with the freshest would overstate how live it is.
    """
    stamps = [stamp for stamp in candidates if stamp is not None]
    return min(stamps) if stamps else None
