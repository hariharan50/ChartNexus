"""Turning one set of thresholds into bands that mean the same thing on every index.

The bug this module exists to fix: ``LevelBands`` is in points, and a single
point value cannot serve NIFTY, BANKNIFTY and SENSEX at once.

=============  =======  ============  ========================
instrument       price   daily range   a 12-point buffer is...
=============  =======  ============  ========================
NIFTY           24,650        ~200     6.0% of the range
BANKNIFTY       52,000        ~650     1.8% of the range
SENSEX          81,000        ~800     1.5% of the range
=============  =======  ============  ========================

At 1.5% of the day's range the buffer sits *inside the tick noise*: price
crosses it many times a minute, chop routinely survives the twenty-second hold,
and the engine confirms breaks that never happened. The mirror failure is a
six-point touch band on an 81,000 index — narrower than the gap between
consecutive ticks, so touches are missed outright. One false-alert mode and one
missed-alert mode, from the same constant.

The fix is the one the shared kernel already names in ``levels.py``: express a
distance as a multiple of ATR, because that is the number that transfers
between instruments. **Distances scale; times and counts do not** — twenty
seconds of conviction is twenty seconds on any index, and a cap of three alerts
is about the reader's patience, not about price.

Pure and ATR-injected, so the whole scaling story is testable without a feed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from chartnexus.contexts.trade_buddy.domain.level import LevelBands

#: Defaults chosen so NIFTY behaves exactly as it did before this module
#: existed. NIFTY's ATR(14) sits near 200 points, and 0.03/0.125/0.06 of that
#: is 6/25/12 — the previous hardcoded constants. The same multiples give
#: roughly 21/87/42 on BANKNIFTY and 24/100/48 on SENSEX.
DEFAULT_TOUCH_MULTIPLE = 0.03
DEFAULT_APPROACH_MULTIPLE = 0.125
DEFAULT_BREAK_MULTIPLE = 0.06


class BandSource(StrEnum):
    """How the bands in use were arrived at. Surfaced on the page.

    ``POINTS`` is a degraded state, not an equivalent one: it means every
    instrument is being measured with the same ruler again. It is reported
    rather than hidden, because silently applying NIFTY-sized bands to
    BANKNIFTY is precisely the bug this module fixes.
    """

    ATR = "atr"
    POINTS = "points"


@dataclass(frozen=True, slots=True)
class BandMultiples:
    """The three distance bands, as fractions of ATR."""

    touch: float = DEFAULT_TOUCH_MULTIPLE
    approach: float = DEFAULT_APPROACH_MULTIPLE
    break_buffer: float = DEFAULT_BREAK_MULTIPLE

    def __post_init__(self) -> None:
        if self.touch <= 0 or self.approach <= 0 or self.break_buffer <= 0:
            raise ValueError("band multiples must all be positive")
        if self.touch > self.approach:
            raise ValueError(
                f"touch multiple ({self.touch}) must not exceed approach multiple ({self.approach})"
            )


@dataclass(frozen=True, slots=True)
class BandOverrides:
    """Explicit point values that win over the ATR calculation.

    For the case the multiples cannot express: a level on a round number the
    whole market watches may deserve a wider buffer than its instrument's
    volatility alone suggests. ``None`` means "scale it from ATR".
    """

    touch: float | None = None
    approach: float | None = None
    break_buffer: float | None = None
    confirm_hold_seconds: float | None = None

    @property
    def empty(self) -> bool:
        return (
            self.touch is None
            and self.approach is None
            and self.break_buffer is None
            and self.confirm_hold_seconds is None
        )


@dataclass(frozen=True, slots=True)
class AlertOverrides:
    """Everything one instrument may override, in one object.

    The distance bands scale with ATR and the throttles do not — but "does not
    scale automatically" is not the same as "cannot be set per instrument". On
    a day spent in BANKNIFTY you want a shorter cooldown there and the usual
    one elsewhere, so all six are per-instrument and the panel has one rule to
    explain rather than two.
    """

    bands: BandOverrides = field(default_factory=BandOverrides)
    #: Minutes between repeat observations of the same kind on one level.
    cooldown_minutes: float | None = None
    #: Observation alerts per level per day. Confirmed breaks ignore this.
    daily_alert_cap: int | None = None

    @property
    def empty(self) -> bool:
        return self.bands.empty and self.cooldown_minutes is None and self.daily_alert_cap is None


@dataclass(frozen=True, slots=True)
class ResolvedBands:
    """The bands actually in force, and the story of where they came from."""

    bands: LevelBands
    source: BandSource
    #: The ATR the scaling used, or ``None`` when it was unavailable.
    atr: float | None
    #: Set when a stored override was unusable and was ignored. Shown on the
    #: page: an override that silently does nothing is worse than one rejected.
    note: str | None = None

    @property
    def scaled(self) -> bool:
        return self.source is BandSource.ATR


@dataclass(frozen=True, slots=True)
class BandPolicy:
    """Everything needed to turn an ATR into bands, bundled.

    Passed as one object so the engine takes a policy rather than six loose
    numbers, and so the request side and the worker cannot drift on any of
    them — they are built from the same settings by the same function.
    """

    multiples: BandMultiples
    #: Point values used when ATR is unavailable, and the shape results are
    #: validated against.
    fallback: LevelBands
    confirm_hold_seconds: float
    atr_period: int = 14


def resolve_bands(
    *,
    atr: float | None,
    multiples: BandMultiples,
    fallback: LevelBands,
    overrides: BandOverrides | None = None,
    confirm_hold_seconds: float,
) -> ResolvedBands:
    """The bands for one instrument right now.

    ``fallback`` supplies the point values used when ATR is unavailable, and
    also the shape every result is validated against. ``confirm_hold_seconds``
    is passed separately because it is a duration and never scales.

    Never raises. A watcher that dies because a hand-edited override is
    nonsensical has turned a cosmetic problem into a missed break, so a bad
    input degrades to the fallback and says so in ``note``.
    """
    overrides = overrides or BandOverrides()
    hold = overrides.confirm_hold_seconds
    hold = confirm_hold_seconds if hold is None else hold

    usable_atr = atr if atr is not None and atr > 0 else None

    if usable_atr is None:
        scaled = LevelBands(
            touch=fallback.touch,
            approach=fallback.approach,
            break_buffer=fallback.break_buffer,
            confirm_hold_seconds=hold,
        )
        source = BandSource.POINTS
    else:
        scaled = LevelBands(
            touch=usable_atr * multiples.touch,
            approach=usable_atr * multiples.approach,
            break_buffer=usable_atr * multiples.break_buffer,
            confirm_hold_seconds=hold,
        )
        source = BandSource.ATR

    if overrides.empty:
        return ResolvedBands(bands=scaled, source=source, atr=usable_atr)

    try:
        overridden = LevelBands(
            touch=overrides.touch if overrides.touch is not None else scaled.touch,
            approach=(overrides.approach if overrides.approach is not None else scaled.approach),
            break_buffer=(
                overrides.break_buffer
                if overrides.break_buffer is not None
                else scaled.break_buffer
            ),
            confirm_hold_seconds=hold,
        )
    except ValueError as exc:
        return ResolvedBands(
            bands=scaled,
            source=source,
            atr=usable_atr,
            note=f"Override ignored: {exc}",
        )

    return ResolvedBands(bands=overridden, source=source, atr=usable_atr)
