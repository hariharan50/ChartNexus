"""Price Action skill — trend and volatility regime off the candle history.

Three reads, blended:

* **Trend** — a fast/slow EMA relationship when there are enough bars, falling
  back to a simple slope over the recent window when there are not. Fast above
  slow (or a rising slope) is bullish.
* **Location vs. max pain** — price stretched well above the max-pain magnet
  leans bearish (pull back toward pain) and vice-versa; near pain says nothing.
* **Volatility regime** — ATR relative to price only *scales* conviction: a
  trend in a calm tape is more reliable than the same trend in a whippy one, so
  a high ATR shrinks the score rather than flipping it.

Weight 2.0.
"""

from __future__ import annotations

from marketcompass.contexts.signals.domain.indicators import atr, clamp, ema, slope_pct
from marketcompass.contexts.signals.domain.inputs import MarketSnapshot
from marketcompass.contexts.signals.domain.models import SkillRead

WEIGHT = 2.0
_LABEL = "Price Action"
_SKILL = "price_action"

_FAST = 9
_SLOW = 21
_SLOPE_LOOKBACK = 10
# Above this ATR-to-price fraction the tape is choppy enough to discount trend.
_HOT_ATR = 0.02
# Score magnitude past which a read is called trending rather than rangebound.
_LEAN = 0.15
# Below this |stretch| spot is effectively at max pain — no location signal.
_FLAT_STRETCH = 0.001


def analyse(snap: MarketSnapshot) -> SkillRead:
    parts: list[float] = []
    details: list[str] = []

    trend = _score_trend(snap, details)
    if trend is not None:
        parts.append(trend)

    location = _score_location(snap, details)
    if location is not None:
        parts.append(location)

    if not parts:
        return SkillRead(
            skill=_SKILL,
            label=_LABEL,
            weight=WEIGHT,
            score=None,
            headline="Not enough price history to read a trend.",
            details=(),
        )

    raw = sum(parts) / len(parts)
    score = clamp(raw * _volatility_scale(snap, details))
    return SkillRead(
        skill=_SKILL,
        label=_LABEL,
        weight=WEIGHT,
        score=score,
        headline=_headline(score),
        details=tuple(details),
    )


def _score_trend(snap: MarketSnapshot, details: list[str]) -> float | None:
    fast = ema(snap.closes, _FAST)
    slow = ema(snap.closes, _SLOW)
    if fast is not None and slow is not None and slow > 0.0:
        gap = (fast - slow) / slow
        # A 1% EMA gap is already a firm trend; saturate there.
        score = clamp(gap * 100.0)
        direction = "up" if score > 0 else "down"
        details.append(f"Fast EMA {'above' if score > 0 else 'below'} slow — {direction}-trend.")
        return score

    slope = slope_pct(snap.closes, _SLOPE_LOOKBACK)
    if slope is not None:
        score = clamp(slope * 50.0)
        details.append(f"Recent slope {slope * 100:+.1f}% over {_SLOPE_LOOKBACK} bars.")
        return score
    return None


def _score_location(snap: MarketSnapshot, details: list[str]) -> float | None:
    if snap.max_pain is None or snap.max_pain <= 0.0 or snap.spot <= 0.0:
        return None
    stretch = (snap.spot - snap.max_pain) / snap.max_pain
    if abs(stretch) < _FLAT_STRETCH:
        return None
    # Stretched above pain leans bearish (mean-revert down toward the magnet).
    score = clamp(-stretch * 40.0)
    where = "above" if stretch > 0 else "below"
    details.append(f"Spot {abs(stretch) * 100:.1f}% {where} max pain {snap.max_pain:,.0f}.")
    return score


def _volatility_scale(snap: MarketSnapshot, details: list[str]) -> float:
    value = atr(snap.highs, snap.lows, snap.closes)
    if value is None or snap.spot <= 0.0:
        return 1.0
    fraction = value / snap.spot
    if fraction >= _HOT_ATR:
        details.append(f"ATR {fraction * 100:.1f}% of spot — choppy, conviction trimmed.")
        return 0.6
    return 1.0


def _headline(score: float) -> str:
    if score > _LEAN:
        return "Price action is trending up."
    if score < -_LEAN:
        return "Price action is trending down."
    return "Price action is rangebound."
