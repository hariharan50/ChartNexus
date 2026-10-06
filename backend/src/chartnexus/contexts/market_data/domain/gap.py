"""The overnight gap: where a session opened against the close it opened from.

Two rules shape everything here, and both exist because of a bug this module
replaces.

**The opening print is a fact, not a reading.** The dashboard used to recompute
``open - previous_close`` from whatever the fifteen-second spot poll happened to
carry. A broker hiccup dropped that poll onto the mock provider, whose seeded
walk has its own open and its own previous close, and the card flipped from
+125 to -120 and back as the circuit breaker opened and reset. So a gap is
*observed once* and then latched for the session; a later observation may only
replace it if it comes from a strictly more trustworthy source, or if the
opening auction had not yet settled when the first one was taken.

**A pair that cannot be true is not a pair.** A zero open, a zero reference
close, or an open twenty percent away from the close or from the live price is
a data error, not a gap. It is rejected here rather than rendered, because a
card that says GAP DOWN -2,400 is worse than one that says it does not know.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from chartnexus.contexts.market_data.domain.market_data import DataSource


class GapSignal(StrEnum):
    """The verdict a reader acts on."""

    UP = "gap_up"
    DOWN = "gap_down"
    FLAT = "flat"


#: Below this the open is treated as level with the previous close. Roughly 35
#: points on a 23,500 NIFTY - wide enough to swallow ordinary overnight noise,
#: narrow enough that a gap a trader would act on still reads as one. Defined
#: here once so GAP UP / GAP DOWN / FLAT means one thing wherever it is shown —
#: a second threshold elsewhere would have two pages disagree about the same
#: morning.
FLAT_PERCENT: Decimal = Decimal("0.15")

#: The widest gap that can be a gap. NSE halts the market at a 20% index move,
#: so anything past it is a bad print, a stale field, or two sessions' figures
#: paired by accident. Rejecting is the point: this is the guard that stops a
#: mock open being divided by a live close.
MAX_PLAUSIBLE_PERCENT: Decimal = Decimal("20")


@dataclass(frozen=True, slots=True)
class SessionGap:
    """One session's opening gap, with the provenance of the pair it came from.

    ``source`` and ``settled`` are not decoration. ``source`` is what lets a
    live reading refuse to be overwritten by a synthetic one, and ``settled``
    is what lets a pre-open placeholder be overwritten by the real opening
    print once the auction has run.
    """

    opened_at: Decimal
    """The session's opening print."""

    reference_close: Decimal
    """The previous session's close - what the gap is measured from."""

    points: Decimal
    percent: Decimal
    signal: GapSignal

    source: DataSource
    """Where the pair came from. A latched ``LIVE`` gap outranks everything."""

    observed_at: datetime
    """When the pair was taken. Shown, so a reader can see it is not ticking."""

    settled: bool
    """Whether the opening auction had run when this was observed.

    ``False`` for a pair taken before the open, which brokers fill with the
    *previous* session's figures. Such a reading is provisional and any
    same-rank observation replaces it; a settled one is frozen for the day.
    """


#: How much a source is trusted, for deciding whether a new observation may
#: replace a latched one. Higher wins.
_RANK: dict[DataSource, int] = {
    DataSource.MOCK: 0,
    DataSource.CACHED: 1,
    DataSource.LIVE: 2,
}


def measure(
    day_open: Decimal | None,
    previous_close: Decimal | None,
    *,
    source: DataSource,
    observed_at: datetime,
    settled: bool,
    reference_price: Decimal | None = None,
) -> SessionGap | None:
    """The gap, or ``None`` when the pair cannot be believed.

    ``reference_price`` is the quote's own last price, used only as a sanity
    check: an open that is nowhere near the price printed beside it did not come
    from the same session as that price.
    """
    if day_open is None or previous_close is None:
        return None
    if day_open <= 0 or previous_close <= 0:
        return None

    points = day_open - previous_close
    percent = points / previous_close * Decimal(100)
    if abs(percent) > MAX_PLAUSIBLE_PERCENT:
        return None
    if not _near(day_open, reference_price):
        return None

    return SessionGap(
        opened_at=day_open,
        reference_close=previous_close,
        points=points,
        percent=percent,
        signal=classify(percent),
        source=source,
        observed_at=observed_at,
        settled=settled,
    )


def classify(percent: Decimal) -> GapSignal:
    """GAP UP, GAP DOWN, or FLAT, against the shared dead zone."""
    if abs(percent) < FLAT_PERCENT:
        return GapSignal.FLAT
    return GapSignal.UP if percent > 0 else GapSignal.DOWN


def supersedes(observed: SessionGap, latched: SessionGap) -> bool:
    """Whether a fresh observation may replace the one already latched.

    Only two things justify rewriting a session's opening print:

    * the new pair comes from a better source - a live quote displacing the
      mock that stood in for it while the broker was unreachable; or
    * the latched pair was taken before the opening auction settled, so it was
      never the opening print in the first place.

    Everything else is the same fact observed again, and re-latching it would
    reintroduce exactly the flapping this module exists to stop.
    """
    if _RANK[observed.source] > _RANK[latched.source]:
        return True
    return not latched.settled and _RANK[observed.source] >= _RANK[latched.source]


def _near(value: Decimal, reference: Decimal | None) -> bool:
    """Whether ``value`` is within the plausible band of ``reference``.

    A missing or non-positive reference abstains rather than rejecting - the
    check is a guard against mismatched sessions, not a required input.
    """
    if reference is None or reference <= 0:
        return True
    return abs(value - reference) / reference * Decimal(100) <= MAX_PLAUSIBLE_PERCENT
