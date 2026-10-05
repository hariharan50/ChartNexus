"""The overnight gap, and how big a gap this actually is.

A gap in points is almost useless on its own and a gap in percent is only
slightly better. Sixty points on NIFTY is a shrug when the average day travels
two hundred and fifty, and an event when it travels eighty. So the bucket that
feeds every conditional statistic downstream is **ATR-relative**, not a fixed
percentage.

That choice matters more than it looks. A fixed ±0.3% band would file a
sleepy-market gap and a crisis-market gap into the same bucket, and every
"sessions that looked like this" figure computed from those buckets would be
quietly averaging two different market regimes. The percent bands are kept as
a fallback for when ATR is unavailable, and the reading says which was used.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from chartnexus.shared_kernel.domain.statistics import bucket


class GapBucket(StrEnum):
    """The vocabulary every fingerprint dimension and statistic shares."""

    DOWN_LARGE = "gap_down_large"
    DOWN = "gap_down"
    FLAT = "flat"
    UP = "gap_up"
    UP_LARGE = "gap_up_large"


class GapBasis(StrEnum):
    """What the bucket was measured against."""

    ATR = "atr"
    PERCENT = "percent"


#: In ATR multiples. A quarter-ATR gap is inside the noise of an ordinary
#: session; a full ATR before the open is a different kind of morning.
_ATR_EDGES = (-1.0, -0.25, 0.25, 1.0)

#: The fallback when no ATR is available. 0.15% matches the dead zone the
#: dashboard's gap card and GIA's implied open already use, so GAP UP / GAP
#: DOWN / FLAT means one thing product-wide.
_PERCENT_EDGES = (-1.0, -0.15, 0.15, 1.0)

_LABELS = (
    GapBucket.DOWN_LARGE.value,
    GapBucket.DOWN.value,
    GapBucket.FLAT.value,
    GapBucket.UP.value,
    GapBucket.UP_LARGE.value,
)


@dataclass(frozen=True, slots=True)
class Gap:
    """Where a session opened against the close it opened from."""

    points: Decimal
    percent: Decimal
    bucket: GapBucket
    basis: GapBasis
    #: How many ATRs the gap spans. ``None`` when no ATR was available — which
    #: is also why ``basis`` would then read ``percent``.
    atr_multiple: float | None
    reference_close: Decimal
    opened_at: Decimal


def measure(
    day_open: Decimal | None,
    previous_close: Decimal | None,
    *,
    atr: float | None = None,
) -> Gap | None:
    """The gap, bucketed against ATR where possible.

    ``None`` when either leg is missing — before the open there is no
    ``day_open`` at all, and inventing one from the GIFT-implied level would
    present a derived number in the slot reserved for an observed one.
    """
    if day_open is None or previous_close is None or previous_close <= 0:
        return None

    points = day_open - previous_close
    percent = points / previous_close * Decimal(100)

    if atr and atr > 0:
        multiple = float(points) / atr
        return Gap(
            points=points,
            percent=percent,
            bucket=GapBucket(bucket(multiple, _ATR_EDGES, _LABELS)),
            basis=GapBasis.ATR,
            atr_multiple=multiple,
            reference_close=previous_close,
            opened_at=day_open,
        )

    return Gap(
        points=points,
        percent=percent,
        bucket=GapBucket(bucket(float(percent), _PERCENT_EDGES, _LABELS)),
        basis=GapBasis.PERCENT,
        atr_multiple=None,
        reference_close=previous_close,
        opened_at=day_open,
    )


def implied(
    gift_level: Decimal | None,
    previous_close: Decimal | None,
    *,
    atr: float | None = None,
) -> Gap | None:
    """The gap GIFT NIFTY is quoting, before the cash market opens.

    Same arithmetic as :func:`measure`, kept as a separate name because the two
    are different claims: one is what happened, the other is what one contract
    thinks will happen. A page that renders them in the same slot without
    saying which is which invites the reader to treat a quote as a print.
    """
    return measure(gift_level, previous_close, atr=atr)


def agreement(actual: Gap | None, quoted: Gap | None) -> str | None:
    """Whether the realised gap went the way GIFT quoted it.

    ``None`` until both exist. The interesting state is ``diverged``: the
    contract that settles to NIFTY said one thing and the open did another,
    which is a fact about overnight positioning worth seeing rather than
    averaging away.
    """
    if actual is None or quoted is None:
        return None
    if actual.bucket is GapBucket.FLAT or quoted.bucket is GapBucket.FLAT:
        return "inconclusive"
    actual_up = actual.points > 0
    quoted_up = quoted.points > 0
    return "aligned" if actual_up == quoted_up else "diverged"
