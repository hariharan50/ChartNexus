"""The overnight handoff: what the world did while India slept, and what it implies.

This is the module the whole page exists for. A list of nine index quotes
leaves the inference to the reader; everything here does that inference
explicitly, and — just as importantly — shows its working.

**The organising idea.** A trading day passes around the globe like a baton.
India closes at 15:30 IST; Europe is still running; New York opens at 19:00 IST
and closes at 01:30; GIFT NIFTY trades through most of the night; then India
opens at 09:15 and inherits all of it. The window between one Indian close and
the next Indian open is the only interval that matters, and everything below is
scoped to it.

**Two independent reads, deliberately kept apart.**

*Global Gap Pressure* is a weighted composite of what the world's markets did
in that window. *Implied open* is GIFT NIFTY's own premium to NIFTY spot. They
answer the same question by different routes: the composite infers, GIFT
quotes. Merging them into one number would destroy the most useful thing on the
page — when the two disagree, that disagreement is the reading.

**Nothing here is a prediction the page can hide behind.** ``GapPressure``
carries every contribution that went into it, so the UI renders a waterfall
rather than an oracle. A score whose inputs cannot be inspected is not
analysis, it is a horoscope with a decimal point.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Final

from chartnexus.contexts.global_markets.domain.markets import (
    IST,
    NIFTY_CLOSE,
    NIFTY_OPEN,
    SCORED,
    GlobalMarket,
    session_window,
)
from chartnexus.contexts.global_markets.domain.quotes import GlobalQuote, QuoteSet

ZERO = Decimal("0")

#: ``date.weekday()`` of Friday. Anything above it is the weekend.
FRIDAY = 4


# -- the window ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OvernightWindow:
    """The span from India's last close to its next open, in IST."""

    opened_at: datetime
    closes_at: datetime
    #: The Indian session this window leads *into* — the one whose gap is
    #: being predicted.
    target_session: date

    @property
    def total_seconds(self) -> float:
        return (self.closes_at - self.opened_at).total_seconds()

    def progress(self, now: datetime) -> float:
        """How far through the window ``now`` is, clamped to 0…1."""
        elapsed = (now.astimezone(IST) - self.opened_at).total_seconds()
        return max(0.0, min(1.0, elapsed / self.total_seconds))


def overnight_window(now: datetime) -> OvernightWindow:
    """The handoff window ``now`` falls in.

    Which window is "current" turns on the Indian *close*, not the open:

    * **Before 15:30** the window on screen is the one that produced this
      morning's open. Someone checking GIA at 11:00 wants to know what drove
      the session they are trading, and that handoff has already finished.
    * **After 15:30** the baton has been passed again. The new window is
      running and targets the *next* trading day, so the New York session
      opening at 19:00 IST lands inside it instead of falling off the end.

    That boundary is not cosmetic. A window still pinned to this morning at
    23:00 would exclude the live US session entirely, which is the single
    loudest input the page has.
    """
    local = now.astimezone(IST)
    today = local.date()
    close_today = datetime.combine(today, NIFTY_CLOSE, tzinfo=IST)

    target = _next_weekday(today) if local >= close_today else today

    closes_at = datetime.combine(target, NIFTY_OPEN, tzinfo=IST)
    opened_at = datetime.combine(_previous_weekday(target), NIFTY_CLOSE, tzinfo=IST)
    return OvernightWindow(opened_at=opened_at, closes_at=closes_at, target_session=target)


def _previous_weekday(day: date) -> date:
    """The weekday before ``day``, skipping the weekend.

    A Monday's overnight window opens at Friday's close, not at a Sunday
    session that never traded. Exchange holidays are not modelled: a holiday
    simply leaves that market's band flat, which is what actually happened.
    """
    previous = day - timedelta(days=1)
    weekend = previous.weekday() - FRIDAY
    if weekend > 0:
        previous -= timedelta(days=weekend)
    return previous


def _next_weekday(day: date) -> date:
    """The weekday after ``day``. Friday evening's window targets Monday."""
    following = day + timedelta(days=1)
    while following.weekday() > FRIDAY:
        following += timedelta(days=1)
    return following


# -- bands --------------------------------------------------------------------


class BandState(StrEnum):
    PENDING = "pending"
    LIVE = "live"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class SessionBand:
    """One market's session, placed on the window's IST axis."""

    key: str
    label: str
    region: str
    opens_at: datetime
    closes_at: datetime
    state: BandState
    #: 0…1 positions within the window, so the UI does no date arithmetic.
    start_fraction: float
    end_fraction: float
    change_percent: Decimal | None


def session_bands(
    window: OvernightWindow, quotes: QuoteSet, now: datetime
) -> tuple[SessionBand, ...]:
    """Every scored market's session, positioned on the handoff axis.

    A band is placed on whichever of its own sessions actually falls inside
    the window. New York's session on the window's opening date lands at
    19:00-01:30 IST and therefore inside it; Tokyo's session on the *closing*
    date lands at 05:30-12:00 IST and also inside it. Picking the wrong local
    date for either would draw the band a full day out of place, which is the
    single easiest way to make this chart lie.
    """
    local_now = now.astimezone(IST)
    bands: list[SessionBand] = []

    for market in SCORED:
        placed = _place(market, window)
        if placed is None:
            continue
        opens_at, closes_at = placed

        if local_now < opens_at:
            state = BandState.PENDING
        elif local_now >= closes_at:
            state = BandState.CLOSED
        else:
            state = BandState.LIVE

        quote = quotes.get(market.key)
        bands.append(
            SessionBand(
                key=market.key,
                label=market.label,
                region=market.region.value,
                opens_at=opens_at,
                closes_at=closes_at,
                state=state,
                start_fraction=_fraction(window, opens_at),
                end_fraction=_fraction(window, closes_at),
                change_percent=quote.change_percent if quote else None,
            )
        )

    bands.sort(key=lambda band: band.opens_at)
    return tuple(bands)


def _place(market: GlobalMarket, window: OvernightWindow) -> tuple[datetime, datetime] | None:
    """The market session that overlaps ``window``, if any.

    Tries the window's opening local date and its closing one, and keeps
    whichever overlaps. Both are tried because the same window contains a US
    session dated the day before the Indian open and an Asian session dated
    the same day as it.
    """
    for session in (window.opened_at.date(), window.closes_at.date()):
        opens_at, closes_at = session_window(market, session)
        if closes_at > window.opened_at and opens_at < window.closes_at:
            return opens_at, closes_at
    return None


def _fraction(window: OvernightWindow, moment: datetime) -> float:
    elapsed = (moment - window.opened_at).total_seconds()
    return max(0.0, min(1.0, elapsed / window.total_seconds))


# -- the composite ------------------------------------------------------------

#: Scales the weighted sum of percentage moves into the -100…+100 band.
#:
#: Calibrated so an ordinary night — the S&P down 1%, Europe down 0.4%, Asia
#: flat — lands around -45, in the "down" band rather than pinned at the
#: extreme. A composite that saturates on a normal session cannot distinguish
#: a bad night from a crisis, which is the distinction it exists to draw.
PRESSURE_SCALE: Final = Decimal("28")

#: Below this the composite is calling the open level. Matches the dashboard's
#: gap dead-zone so GAP UP / GAP DOWN / FLAT means one thing product-wide.
FLAT_GAP_PERCENT: Final = Decimal("0.15")

_STRONG = Decimal("55")
_MILD = Decimal("18")

#: Floor on the recency multiplier. A market that closed fourteen hours ago
#: still carries information — the US close is old news by the Indian open and
#: is still the loudest input there is — so the decay flattens rather than
#: reaching zero.
_RECENCY_FLOOR = Decimal("0.35")


class PressureBand(StrEnum):
    STRONG_DOWN = "strong_down"
    DOWN = "down"
    FLAT = "flat"
    UP = "up"
    STRONG_UP = "strong_up"


@dataclass(frozen=True, slots=True)
class Contribution:
    """One market's share of the composite, with everything that produced it."""

    key: str
    label: str
    region: str
    change_percent: Decimal
    weight: Decimal
    recency: Decimal
    #: ``change_percent x weight x recency x PRESSURE_SCALE``.
    points: Decimal


@dataclass(frozen=True, slots=True)
class GapPressure:
    """The composite read, and every input that made it."""

    score: Decimal
    band: PressureBand
    contributions: tuple[Contribution, ...]
    #: Markets with a weight that had no usable quote. Named rather than
    #: silently dropped: a composite built from four of nine inputs is a
    #: different claim from one built from all nine.
    missing: tuple[str, ...]


def gap_pressure(window: OvernightWindow, quotes: QuoteSet, now: datetime) -> GapPressure:
    """Weigh what the world did in ``window`` into one -100…+100 reading.

    Each market contributes its percentage move, scaled by its pull on the
    Indian gap and by how recently it closed. The recency term is the piece a
    quote table cannot express: at 09:00 IST, Tokyo is still trading and the
    S&P closed seven hours ago, and those two facts do not deserve equal
    billing in a forecast of the open twenty minutes from now.
    """
    contributions: list[Contribution] = []
    missing: list[str] = []
    total = ZERO

    for market in SCORED:
        quote = quotes.get(market.key)
        if quote is None or quote.change_percent is None:
            missing.append(market.key)
            continue

        recency = _recency(market, window, now)
        points = (quote.change_percent * market.gap_weight * recency * PRESSURE_SCALE).quantize(
            Decimal("0.01")
        )
        total += points
        contributions.append(
            Contribution(
                key=market.key,
                label=market.label,
                region=market.region.value,
                change_percent=quote.change_percent,
                weight=market.gap_weight,
                recency=recency,
                points=points,
            )
        )

    score = max(Decimal("-100"), min(Decimal("100"), total)).quantize(Decimal("0.01"))
    # Largest mover first: the waterfall should lead with whatever actually
    # drove the number, not with whichever market happens to sort first.
    contributions.sort(key=lambda item: abs(item.points), reverse=True)
    return GapPressure(
        score=score,
        band=_band(score),
        contributions=tuple(contributions),
        missing=tuple(missing),
    )


def _recency(market: GlobalMarket, window: OvernightWindow, now: datetime) -> Decimal:
    """How much a market's move still counts, by how long ago it closed.

    Full weight while it is still trading, then decaying linearly to
    :data:`_RECENCY_FLOOR` at the far end of the window.
    """
    placed = _place(market, window)
    if placed is None:
        return Decimal("1")
    _, closes_at = placed

    local_now = now.astimezone(IST)
    if local_now <= closes_at:
        return Decimal("1")

    span = (window.closes_at - closes_at).total_seconds()
    if span <= 0:
        return Decimal("1")

    aged = min(1.0, (local_now - closes_at).total_seconds() / span)
    decayed = Decimal("1") - (Decimal("1") - _RECENCY_FLOOR) * Decimal(str(round(aged, 4)))
    return decayed.quantize(Decimal("0.001"))


def _band(score: Decimal) -> PressureBand:
    if score <= -_STRONG:
        return PressureBand.STRONG_DOWN
    if score <= -_MILD:
        return PressureBand.DOWN
    if score >= _STRONG:
        return PressureBand.STRONG_UP
    if score >= _MILD:
        return PressureBand.UP
    return PressureBand.FLAT


# -- implied open -------------------------------------------------------------


class GapSignal(StrEnum):
    GAP_UP = "gap_up"
    GAP_DOWN = "gap_down"
    FLAT = "flat"


@dataclass(frozen=True, slots=True)
class ImpliedOpen:
    """What GIFT NIFTY is quoting the Indian open at."""

    gift_level: Decimal
    #: GIFT's own session move, against its *own* previous settlement — the
    #: figure every broker screen and chart prints beside the contract.
    #: Carried so this card can be reconciled against them. It is a different
    #: reading from the gap below, which is measured against NIFTY, and a card
    #: that shows only one of the two invites the reader to conclude the other
    #: is broken.
    gift_change: Decimal | None
    gift_change_percent: Decimal | None
    nifty_spot: Decimal
    #: The NIFTY close the target session will open *from*. While the cash
    #: market is trading that is the previous settlement; once it has shut for
    #: the day it is the close that just printed, which is ``nifty_spot``.
    reference_close: Decimal
    #: Whether the Indian cash market is trading right now. It is what decides
    #: which close ``reference_close`` holds, so the card labels itself from
    #: it rather than guessing from the numbers.
    nifty_is_trading: bool
    #: GIFT minus spot. Positive is a premium, which is the normal state — the
    #: contract carries cost of carry — so the *change* in basis matters more
    #: than its sign. Shown, not interpreted.
    basis: Decimal
    implied_level: Decimal
    gap_points: Decimal
    gap_percent: Decimal
    signal: GapSignal


def implied_open(
    gift: GlobalQuote | None, nifty: GlobalQuote | None, now: datetime
) -> ImpliedOpen | None:
    """The open GIFT NIFTY implies, or ``None`` if either leg is missing.

    The implied level *is* the GIFT level: the contract settles to NIFTY, so
    what it trades at is the market's own quote of where the index opens.

    **The gap needs the right close, and which close that is moves with the
    clock.** The gap is GIFT against the settlement the next Indian open will
    start from. While the cash market is trading, that settlement is
    *yesterday's* close and spot has already moved away from it. Once the
    market shuts, the close that just printed becomes the one the next open
    gaps from — and it is ``nifty.price``, because the provider's
    ``previous_close`` has by then slipped a full session behind.

    Reading ``previous_close`` in both states is the failure this function was
    rewritten for: overnight it measured the gap from a close two sessions
    old, which on any day the index moved put the card's sign *opposite* to
    the truth — GAP UP printed over a contract trading below the close it
    would open from.

    **Two different bases, deliberately.** The *basis* is GIFT against NIFTY
    spot; the *gap* is GIFT against the reference close. Intraday they are
    different numbers. Overnight they converge, correctly: the index has
    stopped moving, so the close it last printed *is* its spot.
    """
    if gift is None or nifty is None:
        return None

    spot = nifty.price
    trading = nifty_is_trading(nifty, now)
    # Only a live cash session makes the previous settlement the right base;
    # the fallback to spot also covers a provider that published no previous
    # close at all.
    reference = nifty.previous_close if trading and nifty.previous_close is not None else spot
    if reference <= 0 or spot <= 0:
        return None

    gap_points = gift.price - reference
    gap_percent = (gap_points / reference * Decimal(100)).quantize(Decimal("0.01"))

    return ImpliedOpen(
        gift_level=gift.price,
        gift_change=gift.change,
        gift_change_percent=gift.change_percent,
        nifty_spot=spot,
        reference_close=reference,
        nifty_is_trading=trading,
        basis=(gift.price - spot).quantize(Decimal("0.01")),
        implied_level=gift.price,
        gap_points=gap_points.quantize(Decimal("0.01")),
        gap_percent=gap_percent,
        signal=gap_signal(gap_percent),
    )


def nifty_is_trading(nifty: GlobalQuote, now: datetime) -> bool:
    """Whether the Indian cash session is actually live at ``now``.

    The clock alone is not enough. 11:00 on a Saturday, or on Diwali, sits
    inside 09:15-15:30 and nothing is trading — and treating those as live
    would measure the gap from a close a session too far back, which is the
    exact error this guard exists to stop. So the quote's own last print has
    to be dated today as well.

    A provider that publishes no print timestamp falls back to the hours,
    which is right on every trading day and wrong only in the direction of
    the old behaviour on a holiday.
    """
    local = now.astimezone(IST)
    if not (NIFTY_OPEN <= local.time() < NIFTY_CLOSE):
        return False
    session = nifty.session
    return session is None or session.astimezone(IST).date() == local.date()


def gap_signal(percent: Decimal) -> GapSignal:
    if abs(percent) < FLAT_GAP_PERCENT:
        return GapSignal.FLAT
    return GapSignal.GAP_UP if percent > 0 else GapSignal.GAP_DOWN


# -- agreement ----------------------------------------------------------------


class Agreement(StrEnum):
    AGREE = "agree"
    DISAGREE = "disagree"
    UNKNOWN = "unknown"


def agreement(pressure: GapPressure, implied: ImpliedOpen | None) -> Agreement:
    """Whether the composite and GIFT are telling the same story.

    The most useful state on the page is ``DISAGREE``: the world's markets
    point one way and the contract that settles to NIFTY points the other. That
    is a genuine signal about positioning, and a page that averaged the two
    into a single arrow would erase it.
    """
    if implied is None:
        return Agreement.UNKNOWN

    composite_up = pressure.band in (PressureBand.UP, PressureBand.STRONG_UP)
    composite_down = pressure.band in (PressureBand.DOWN, PressureBand.STRONG_DOWN)
    if pressure.band is PressureBand.FLAT or implied.signal is GapSignal.FLAT:
        return Agreement.UNKNOWN

    gift_up = implied.signal is GapSignal.GAP_UP
    if (composite_up and gift_up) or (composite_down and not gift_up):
        return Agreement.AGREE
    return Agreement.DISAGREE


# -- region rollup ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegionRollup:
    region: str
    label: str
    #: Simple mean of the members' percentage moves — unweighted on purpose.
    #: This row describes what a *region* did; the weighting belongs to the
    #: composite, and applying it twice would double-count.
    change_percent: Decimal | None
    members: int


def region_rollup(
    markets: Iterable[GlobalMarket], quotes: QuoteSet, label_for: dict[str, str]
) -> tuple[RegionRollup, ...]:
    """What each region did, as a simple mean of its directional indices.

    Two exclusions, both of which produce a visibly wrong number if forgotten:

    * **Inverted instruments.** VIX rises when American equity falls. Averaging
      a 6.8% VIX spike in with three falling US indices prints
      "Americas +1.07%" on a night New York sold off hard - the opposite of
      what happened.
    * **Macro rows.** Crude, gold, the rupee and a bond yield share no unit and
      no direction with each other; their mean is arithmetic on nonsense.

    Unweighted on purpose. This row says what a *region* did; the weighting
    belongs to the composite, and applying it here too would double-count.
    """
    grouped: dict[str, list[Decimal]] = {}
    for market in markets:
        if market.macro or market.inverted:
            continue
        quote = quotes.get(market.key)
        if quote is None or quote.change_percent is None:
            continue
        grouped.setdefault(market.region.value, []).append(quote.change_percent)

    rollups: list[RegionRollup] = []
    for region, moves in grouped.items():
        mean = (sum(moves, ZERO) / Decimal(len(moves))).quantize(Decimal("0.01"))
        rollups.append(
            RegionRollup(
                region=region,
                label=label_for.get(region, region),
                change_percent=mean,
                members=len(moves),
            )
        )
    return tuple(rollups)


# -- the journalled prediction ------------------------------------------------


@dataclass(frozen=True, slots=True)
class GapPrediction:
    """What the page claimed, before the open proved it right or wrong.

    Written every read so a hit-rate scorecard can be built later. Recording
    the prediction is cheap; reconstructing it after the fact is impossible,
    which is why it is journalled now even though nothing reads it yet.
    """

    session: date
    recorded_at: datetime
    pressure_score: Decimal
    pressure_band: PressureBand
    gift_gap_percent: Decimal | None
    gift_signal: GapSignal | None
    #: Filled in after the open by a later pass; ``None`` while pending.
    actual_gap_percent: Decimal | None = None


def prediction_from(
    window: OvernightWindow,
    pressure: GapPressure,
    implied: ImpliedOpen | None,
    now: datetime,
) -> GapPrediction:
    return GapPrediction(
        session=window.target_session,
        recorded_at=now,
        pressure_score=pressure.score,
        pressure_band=pressure.band,
        gift_gap_percent=implied.gap_percent if implied else None,
        gift_signal=implied.signal if implied else None,
    )


def ordered_bands(bands: Sequence[SessionBand]) -> tuple[SessionBand, ...]:
    """Bands in handoff order — by when each session opened."""
    return tuple(sorted(bands, key=lambda band: (band.opens_at, band.key)))
