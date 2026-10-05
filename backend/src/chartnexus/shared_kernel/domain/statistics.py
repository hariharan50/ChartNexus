"""Small descriptive statistics, shared across contexts.

Deliberately boring, and deliberately in one place. Three of these are already
computed inline in two or three modules apiece, in forms that do not quite
agree; a percentile that means one thing on the IV page and another on the
screener is a bug nobody reports because both look plausible.

Same contract as the rest of the shared kernel: **``None`` when the sample is
too small to be honest.** A percentile over four observations is not a
percentile, and returning one invites a reader to act on it.

The distinction this module exists to keep straight is ``percentile_rank``
versus ``rank_in_range``. Every volatility tool ships both and half of them call
both "percentile":

* **Percentile rank** — *how often* has it been this low? Counts observations.
  Robust to one freak spike.
* **Rank in range** — *where in the band* does it sit? Pure min-max. One freak
  spike rescales every reading for a year.

They answer different questions and routinely disagree by twenty points. Naming
them apart is the whole point.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

#: Below this, a percentile is arithmetic on noise.
MIN_SAMPLE = 20

#: A standard deviation needs at least this many points to mean anything.
_MIN_FOR_STDEV = 2


def percentile_rank(
    history: Sequence[float], value: float, *, minimum: int = MIN_SAMPLE
) -> float | None:
    """What percentage of ``history`` sits at or below ``value``.

    ``None`` below ``minimum`` observations. Callers that genuinely want a
    reading off a thin sample must lower the floor explicitly and say so on
    screen — the default refuses rather than flatters.
    """
    if len(history) < minimum:
        return None
    at_or_below = sum(1 for item in history if item <= value)
    return at_or_below / len(history) * 100


def rank_in_range(
    history: Sequence[float], value: float, *, minimum: int = MIN_SAMPLE
) -> float | None:
    """Where ``value`` sits between the sample's min and max, as 0-100.

    The "IV Rank" form. ``None`` when the range is degenerate as well as when
    the sample is thin: a flat history has no band to rank within, and dividing
    by that zero would either raise or silently return a meaningless 0.
    """
    if len(history) < minimum:
        return None
    low, high = min(history), max(history)
    span = high - low
    if span <= 0:
        return None
    return (value - low) / span * 100


def mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def median(values: Sequence[float]) -> float | None:
    """The middle value — preferred over the mean for session outcomes.

    One gap-and-crash session drags a mean far enough to misrepresent the
    typical day, which is exactly the thing a conditional statistic is asked
    about.
    """
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def stdev(values: Sequence[float]) -> float | None:
    """Sample standard deviation, Bessel-corrected."""
    if len(values) < _MIN_FOR_STDEV:
        return None
    average = sum(values) / len(values)
    variance = sum((item - average) ** 2 for item in values) / (len(values) - 1)
    return math.sqrt(variance)


def share(count: int, total: int) -> float | None:
    """``count / total`` as a percentage, or ``None`` when there is no total.

    Exists so no caller writes ``count / total * 100`` and divides by zero on
    the morning the universe comes back empty.
    """
    if total <= 0:
        return None
    return count / total * 100


def bucket(value: float, edges: Sequence[float], labels: Sequence[str]) -> str:
    """Classify ``value`` into one of ``labels`` by ascending ``edges``.

    The one bucketing primitive every fingerprint dimension uses, so the
    vocabularies cannot drift apart. ``labels`` must be exactly one longer than
    ``edges``: with edges ``(-1, 1)`` and labels ``("low", "mid", "high")``,
    a value below -1 is "low", -1 to 1 is "mid", above 1 is "high".
    """
    if len(labels) != len(edges) + 1:
        raise ValueError("bucket() needs exactly one more label than edges.")
    for index, edge in enumerate(edges):
        if value < edge:
            return labels[index]
    return labels[-1]
