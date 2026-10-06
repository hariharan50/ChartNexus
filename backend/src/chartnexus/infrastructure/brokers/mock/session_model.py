"""The one intraday simulation behind every mock price in the app.

There used to be two. ``option_chain_factory`` computed open interest as a
Gaussian around spot peaking near 95,000 a leg, driven by a sine keyed to the
wall-clock minute; the snapshot seeder ran a seeded random walk with an
accumulating book peaking near 3,000,000. The Option Chain page and the Open
Interest page therefore disagreed about the same instrument at the same instant
by roughly thirty times, and starting the ingest worker against a seeded day
appended frames a thirtieth the height of the ones beside them — a cliff in the
middle of the chart.

So this module owns the model and nothing else does. The seeder maps it into
``SnapshotToWrite``, the mock broker maps it into ``OptionChain``, and
``quote_factory.spot_price`` reads its walk. Whatever any of them reports for a
given instrument and instant, the others report too.

Everything is pure and seeded per symbol-day: no clock, no I/O, and the same
inputs always give byte-identical output. That is what lets the seeder be
idempotent and tests assert exact values.

**The grid is fixed at 60 seconds and is not the capture cadence.** Callers
sample it — ``session_frames(interval_seconds=180)`` returns every third frame.
If the grid were the cadence instead, a 60s dev archive and a 180s live chain
would walk different random paths and report different spots for the same
minute, which is the class of bug this module exists to remove.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from functools import lru_cache

from chartnexus.contexts.market_data.domain.instruments import InstrumentSymbol
from chartnexus.infrastructure.catalog import registry
from chartnexus.shared_kernel.domain.errors import ValidationError

# India observes no DST, so a fixed +05:30 offset is correct and avoids needing
# tzdata on the host — the same reasoning every other module here uses.
IST = timezone(timedelta(hours=5, minutes=30))
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)

# The model's internal resolution. Sampling, not cadence — see the module docstring.
MODEL_STEP_SECONDS = 60

# Strikes either side of the opening ATM. A real exchange lists a fixed ladder
# for the session and does not add or drop strikes every minute.
LADDER_REACH = 20

# Per-step volatility, giving roughly a 0.6% daily range over the 376 steps of a
# full session, clamped so no seed produces a limit move.
#
# Kept modest on purpose. A 1.5% day moves spot seven strikes, and since the
# overnight book stays where it was written, the ±10-strike window then shows a
# chain visibly lopsided against the spot line. That is honest for a big day but
# reads as a bug on a screen you look at every morning.
_STEP_SIGMA = 0.00035
_MAX_DRIFT = 0.010

# How tightly OI clusters around its peak, and how far out of the money writers
# prefer to sit, both in strike steps.
#
# The two spreads are what decide whether the peak migrates. A narrow opening
# hump would pin the argmax to the opening ATM for the whole session no matter
# where spot went, because 900k of opening interest swamps the day's writing.
# Broad at open, narrow per step is both realistic (positions are spread across
# a band overnight, then the day's flow concentrates just out of the money) and
# the thing that makes a scrubbed chart change shape rather than just height.
_OPEN_SPREAD = 9.0
_WRITER_SPREAD = 2.5

# How far out of the money each side sits, in strike steps.
#
# Options are written out of the money: calls above spot as resistance, puts
# below as support. Centring both sides on ATM stacks a call and a put of
# near-equal height on every strike and leaves the chain with no shape at all.
# Real chains split, and the split is large: several strikes, not a fraction.
_CALL_OFFSET = 3.0
_PUT_OFFSET = -3.0
# The day's own flow concentrates closer in than the overnight book.
_WRITER_OFFSET = 1.5

_BASE_OPEN_OI = 900_000
# Per 60s step. Roughly a 45% build over a session, matching the old 180s value.
_BASE_STEP_OI = 4_700

# Round strikes carry far more interest than the ones between them: they are
# where round-number strategies, expiring hedges and retail flow all land. A
# chain without this reads as a smooth bell curve, which no real chain is.
_ROUND_500 = 2.2
_ROUND_100 = 1.5
# Where spot has travelled through a strike, writers cover instead of adding.
_UNWIND_AFTER_STEPS = 3.0
_UNWIND_FACTOR = -0.4

CALL = "CE"
PUT = "PE"

# Contract geometry for the simulation comes from the instrument catalog, which
# is populated from the exchange's own symbol master.
#
# It used to be three hand-written dicts, and the comment that stood here
# recorded why that was a bad idea: "earlier values here were guesses scaled off
# NIFTY and were wrong by 5,600 points on BANKNIFTY". Two hundred and nineteen
# instruments make that failure mode a certainty rather than a risk, and the
# lookups had no default, so a missing entry was a KeyError rather than a
# degraded number.
#
# An unknown instrument still raises — but now it is a ValidationError saying
# the symbol is not tradeable, which is the truth.


def base_level(instrument: InstrumentSymbol) -> Decimal:
    """The level the day's walk starts from.

    The catalog derives this from the middle of the listed strike ladder, so it
    is in the right region without anyone re-anchoring it by hand. It is a
    seed, not a price; everything built on it is stamped ``DataSource.MOCK``.
    """
    row = registry.current().get(instrument)
    if row.reference_price is None:
        # Every instrument the symbol master lists has a strike ladder, so this
        # is only reachable for a hand-built catalog row in a test.
        raise ValidationError(
            f"{instrument.value} has no reference price to simulate from.",
            field="instrument",
        )
    return row.reference_price


def strike_step(instrument: InstrumentSymbol) -> Decimal:
    """The gap between adjacent strikes in the synthesised chain."""
    row = registry.current().get(instrument)
    if row.strike_step is None:
        raise ValidationError(
            f"{instrument.value} has no strike step to simulate from.",
            field="instrument",
        )
    return row.strike_step


def lot_size(instrument: InstrumentSymbol) -> int:
    return registry.current().get(instrument).lot_size


@dataclass(frozen=True, slots=True)
class Leg:
    """One side of one strike at one instant."""

    strike: float
    option_type: str
    oi: int
    oi_at_open: int
    ltp: float
    iv: float
    volume: int

    @property
    def oi_change(self) -> int:
        """The day change a broker reports.

        Both consumers must store exactly this: the single-snapshot tier of the
        Open Interest service reconstructs the session open by subtracting it,
        so a fabricated value there silently corrupts the whole tier.
        """
        return self.oi - self.oi_at_open


@dataclass(frozen=True, slots=True)
class SessionFrame:
    """The whole chain at one instant. ``captured_at`` is UTC."""

    captured_at: datetime
    spot: float
    legs: tuple[Leg, ...]

    @property
    def strikes(self) -> tuple[float, ...]:
        return tuple(dict.fromkeys(leg.strike for leg in self.legs))

    def pairs(self) -> list[tuple[float, Leg, Leg]]:
        """``(strike, call, put)`` in ladder order, for row-shaped consumers."""
        calls = {leg.strike: leg for leg in self.legs if leg.option_type == CALL}
        puts = {leg.strike: leg for leg in self.legs if leg.option_type == PUT}
        return [(strike, calls[strike], puts[strike]) for strike in self.strikes]


# -- public API -------------------------------------------------------------


def session_frames(
    symbol: str,
    session_date: date,
    *,
    interval_seconds: int = 180,
    until: datetime | None = None,
) -> list[SessionFrame]:
    """The session sampled at ``interval_seconds``, earliest first.

    ``until`` cuts it off at an instant, which is what capturing *today* must
    do: a real worker cannot have recorded 15:30 at 11:55, and an archive that
    claims otherwise pins the Open Interest tool's "as of" handle to 3:30 pm all
    morning.

    The day is always generated in full and sampled afterwards, so the intraday
    activity curve and time decay shape themselves against the whole session.
    That is also what makes re-seeding later in the day reproduce the earlier
    frames exactly rather than rewriting their history.
    """
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    if interval_seconds % MODEL_STEP_SECONDS != 0:
        raise ValueError(f"interval_seconds must be a multiple of {MODEL_STEP_SECONDS}")

    stride = interval_seconds // MODEL_STEP_SECONDS
    frames = _session(_parse(symbol), session_date)[::stride]
    if until is None:
        return list(frames)
    return [frame for frame in frames if frame.captured_at <= until]


def frame_at(symbol: str, moment: datetime) -> SessionFrame:
    """The frame covering ``moment``, clamped to the session.

    Before the open it answers with the opening frame and after the close with
    the closing one, because the callers — a dashboard, an option-chain page —
    have to render something at 07:41 on a Sunday.
    """
    instrument = _parse(symbol)
    session_date, index = _locate(moment)
    return _session(instrument, session_date)[index]


def spot_at(symbol: str, moment: datetime) -> Decimal:
    """Just the price, without building the chain.

    Split out because the dashboard polls this for three instruments every few
    seconds and has no use for 30,000 option legs.
    """
    instrument = _parse(symbol)
    session_date, index = _locate(moment)
    return _money(_spot_track(instrument, session_date)[index])


def session_open_and_previous_close(
    symbol: str | InstrumentSymbol, moment: datetime
) -> tuple[Decimal, Decimal]:
    """The session's opening print and the prior session's close.

    Both come off the same seeded walk as :func:`spot_at`, so the open a card
    displays always sits within the day's range of the spot beside it. Deriving
    the previous close from a flat base level instead would make every session
    show an identical gap.
    """
    instrument = _parse(symbol)
    session_date, _ = _locate(moment)
    day_open = _money(_spot_track(instrument, session_date)[0])

    previous_date = _previous_session_date(session_date)
    previous_close = _money(_spot_track(instrument, previous_date)[-1])
    return day_open, previous_close


def _previous_session_date(session_date: date) -> date:
    """The trading day before ``session_date``, skipping the weekend.

    The same Saturday/Sunday rule :func:`_locate` applies, so a Monday's gap is
    measured against Friday's close rather than against a session that never
    traded.
    """
    previous = session_date - timedelta(days=1)
    weekend_days = previous.weekday() - 4
    if weekend_days > 0:
        previous -= timedelta(days=weekend_days)
    return previous


def frame_count() -> int:
    """Frames in a full session on the internal grid."""
    return len(_grid(date(2026, 1, 1)))


def spot_track(symbol: str | InstrumentSymbol, session_date: date) -> tuple[float, ...]:
    """One session's seeded walk, one entry per grid step.

    Public because the history factory aggregates whole days of it into candles.
    Reaching into ``_spot_track`` from outside would work and would also make the
    caching and the parsing someone else's problem.
    """
    return _spot_track(_parse(symbol), session_date)


def session_grid(session_date: date) -> tuple[datetime, ...]:
    """The UTC instant of every grid step in a session, aligned with
    :func:`spot_track`."""
    return _grid(session_date)


# -- the walk ---------------------------------------------------------------


def _parse(symbol: str | InstrumentSymbol) -> InstrumentSymbol:
    if isinstance(symbol, InstrumentSymbol):
        return symbol
    return InstrumentSymbol.parse(symbol)


def _grid(session_date: date) -> tuple[datetime, ...]:
    """Every instant on the internal grid, in UTC."""
    first = datetime.combine(session_date, SESSION_OPEN, tzinfo=IST)
    final = datetime.combine(session_date, SESSION_CLOSE, tzinfo=IST)
    step = timedelta(seconds=MODEL_STEP_SECONDS)

    stamps: list[datetime] = []
    moment = first
    while moment <= final:
        stamps.append(moment.astimezone(UTC))
        moment += step
    return tuple(stamps)


def _locate(moment: datetime) -> tuple[date, int]:
    """The session date and grid index ``moment`` falls on.

    A weekend rolls back to Friday. Without it the dashboard would invent a
    fresh Saturday session whose opening gap has no relationship to Friday's
    close, which looks like the price jumped overnight for no reason.
    """
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    local = aware.astimezone(IST)
    session_date = local.date()

    weekend_days = local.weekday() - 4
    if weekend_days > 0:
        session_date -= timedelta(days=weekend_days)
        # Rolled back, so the reading is that day's close.
        return session_date, len(_grid(session_date)) - 1

    opened_at = datetime.combine(session_date, SESSION_OPEN, tzinfo=IST)
    elapsed = (local - opened_at).total_seconds()
    index = int(elapsed // MODEL_STEP_SECONDS)
    return session_date, max(0, min(len(_grid(session_date)) - 1, index))


@lru_cache(maxsize=64)
def _spot_track(instrument: InstrumentSymbol, session_date: date) -> tuple[float, ...]:
    """The seeded price path, one entry per grid step.

    Deliberately not a function of the wall-clock minute the way the old sine
    was: that traced the identical arc every single day, so a scrubbed chart
    looked suspiciously familiar and no two dates could be told apart.
    """
    rng = random.Random(f"{instrument.value}:{session_date.isoformat()}:walk")  # noqa: S311
    spot_open = float(base_level(instrument)) * (1 + rng.uniform(-0.004, 0.004))
    # A small session bias, so not every seeded day drifts the same way.
    drift = rng.uniform(-0.00012, 0.00012)

    floor = spot_open * (1 - _MAX_DRIFT)
    ceiling = spot_open * (1 + _MAX_DRIFT)

    track = [spot_open]
    spot = spot_open
    for _ in range(len(_grid(session_date)) - 1):
        moved = spot * (1 + drift + _STEP_SIGMA * rng.gauss(0, 1))
        spot = min(ceiling, max(floor, moved))
        track.append(spot)
    return tuple(track)


# -- open interest ----------------------------------------------------------


def _affinity(strike: float) -> float:
    """How much more interest a strike attracts for being a round number."""
    if strike % 500 == 0:
        return _ROUND_500
    if strike % 100 == 0:
        return _ROUND_100
    return 1.0


def _opening_oi(strike: float, atm: float, step: float, side: str) -> int:
    """A Gaussian hump, centred out of the money on the side it belongs to."""
    centre = atm + step * (_CALL_OFFSET if side == CALL else _PUT_OFFSET)
    distance = (strike - centre) / (step * _OPEN_SPREAD)
    weight = math.exp(-(distance**2)) * _affinity(strike)
    return round(_BASE_OPEN_OI * weight / 1000.0) * 1000


def _accumulate(
    *,
    oi: dict[tuple[float, str], int],
    ladder: list[float],
    spot: float,
    step: float,
    progress: float,
    rng: random.Random,
) -> None:
    """Add one step's worth of writing to every leg.

    Two things make a scrubbed chart change shape rather than merely grow: the
    peak follows spot (writers sell just out of the money, and spot moves), and
    strikes spot has travelled through unwind instead of building.
    """
    activity = 1.3 - 0.7 * math.sin(math.pi * progress)

    for strike in ladder:
        for side in (CALL, PUT):
            preferred = spot + (_WRITER_OFFSET * step if side == CALL else -_WRITER_OFFSET * step)
            distance = (strike - preferred) / (step * _WRITER_SPREAD)
            pull = math.exp(-(distance**2))

            delta = (
                _BASE_STEP_OI * activity * pull * _affinity(strike) * (1 + 0.35 * rng.gauss(0, 1))
            )

            travelled = (spot - strike) / step
            crossed = (
                travelled > _UNWIND_AFTER_STEPS
                if side == CALL
                else travelled < -_UNWIND_AFTER_STEPS
            )
            if crossed:
                delta *= _UNWIND_FACTOR

            oi[(strike, side)] = max(0, oi[(strike, side)] + int(delta))


@lru_cache(maxsize=8)
def _session(instrument: InstrumentSymbol, session_date: date) -> tuple[SessionFrame, ...]:
    """The whole session, built once per symbol-day.

    Cached because open interest accumulates: reading the 300th frame means
    computing the 299 before it, and the option-chain endpoint asks for one
    frame per request. The bound is small — a session is ~30,000 legs — so this
    holds a few symbol-days, not a history.
    """
    stamps = _grid(session_date)
    track = _spot_track(instrument, session_date)
    step = float(strike_step(instrument))

    atm_open = round(track[0] / step) * step
    ladder = [atm_open + i * step for i in range(-LADDER_REACH, LADDER_REACH + 1)]

    oi_open = {
        (strike, side): _opening_oi(strike, atm_open, step, side)
        for strike in ladder
        for side in (CALL, PUT)
    }
    oi = dict(oi_open)

    rng_oi = random.Random(f"{instrument.value}:{session_date.isoformat()}:oi")  # noqa: S311
    rng_vol = random.Random(f"{instrument.value}:{session_date.isoformat()}:volume")  # noqa: S311

    last = len(stamps) - 1
    frames: list[SessionFrame] = []

    for index, moment in enumerate(stamps):
        spot = track[index]
        progress = index / last if last else 1.0
        if index > 0:
            _accumulate(oi=oi, ladder=ladder, spot=spot, step=step, progress=progress, rng=rng_oi)

        legs = tuple(
            _leg(
                strike=strike,
                side=side,
                spot=spot,
                oi_now=oi[(strike, side)],
                oi_at_open=oi_open[(strike, side)],
                progress=progress,
                rng=rng_vol,
            )
            for strike in ladder
            for side in (CALL, PUT)
        )
        frames.append(SessionFrame(captured_at=moment, spot=spot, legs=legs))

    return tuple(frames)


#: What one at-the-money leg is worth at the open, as a share of spot.
#:
#: A share, not a fixed number of points. The old model charged a flat 140
#: points for every instrument in the catalog — defensible on an index near
#: 24,000, absurd on ASHOKLEY at ₹167.50, where it priced an at-the-money call
#: at 84% of the stock. The universe spans ₹167 to 78,839; only a percentage
#: survives that range.
#:
#: 0.4% a leg puts the NIFTY straddle at ~197, which is what the real
#: near-expiry contract costs — the reference terminal quoted 193.70 on the
#: session this was calibrated against.
_ATM_EXTRINSIC_PCT = 0.004

#: How much of that has bled away by the close.
#:
#: **Calibrated, not chosen: theta collected must equal gamma paid.** A short
#: at-the-money straddle is the cleanest test of whether a synthetic book is
#: internally fair, because it harvests exactly this decay and pays for it in
#: curvature. Re-striking at every strike the market crosses, it should roughly
#: break even over a session and land either side of zero on different days.
#:
#: Swept over six synthetic NIFTY sessions, this lands at a mean of -₹8 a lot
#: inside a ±₹3,300 spread, winning four sessions of six — premium selling's
#: real shape, where the wins are frequent and the losses are bigger. At the old
#: 0.6, against a flat 140-point extrinsic, it was +₹8,421: a book that paid five
#: figures a day for selling premium nothing could ever take back, which is what
#: made the Straddle PnL Simulator draw a one-way ramp into a five-figure loss.
#: Raise this and the seller prints money; drop it and the buyer does.
_DECAY_BY_CLOSE = 0.35


def _leg(
    *,
    strike: float,
    side: str,
    spot: float,
    oi_now: int,
    oi_at_open: int,
    progress: float,
    rng: random.Random,
) -> Leg:
    intrinsic = max(spot - strike, 0.0) if side == CALL else max(strike - spot, 0.0)
    moneyness = abs(strike - spot) / max(spot, 1.0)

    # Extrinsic bleeds away toward the close and with distance from spot.
    #
    # **The width is twice the at-the-money extrinsic, and that is not a tuning
    # choice — it is what makes the at-the-money straddle delta-neutral.**
    #
    # A straddle held at K is worth ``|S-K| + 2·extrinsic(|S-K|)``. With an
    # extrinsic of ``A·exp(-d/W)`` its slope in d is ``1 - (2A/W)·exp(-d/W)``,
    # which is zero at the money exactly when ``W = 2A``. Any other width leaves
    # a first-order term: the previous model decayed over ~575 points against an
    # A of 140, so the at-the-money straddle *rose 0.51 points for every point
    # spot drifted* instead of sitting at a minimum.
    #
    # That is not a cosmetic difference. A short straddle is delta-neutral by
    # construction — it loses to realised volatility through gamma, not to
    # direction — and under the old curve it bled ~₹33 a point deterministically
    # at one NIFTY lot. The Straddle PnL Simulator, which re-strikes all day,
    # compounded that into a five-figure loss on a flat session and drew a
    # relentless downward ramp where the real tool oscillates around zero.
    #
    # Tying W to A also keeps the property as the extrinsic decays: the flat
    # zone narrows into the close, which is gamma rising into expiry — the right
    # behaviour, arrived at for free rather than fitted.
    atm_extrinsic = spot * _ATM_EXTRINSIC_PCT * (1.0 - _DECAY_BY_CLOSE * progress)
    width = max(2.0 * atm_extrinsic, 1e-6)
    extrinsic = atm_extrinsic * math.exp(-abs(strike - spot) / width)

    change = oi_now - oi_at_open
    return Leg(
        strike=strike,
        option_type=side,
        oi=oi_now,
        oi_at_open=oi_at_open,
        ltp=round(intrinsic + extrinsic, 2),
        # Never None anywhere downstream: keeping IV available across the
        # archive is half the reason the archive exists.
        iv=round(12.0 + 9.0 * moneyness * 100.0 / 3.0, 3),
        volume=int(abs(change) * 0.3) + 5_000 + int(rng.random() * 2_000),
    )


def _money(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))
