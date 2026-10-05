"""The seeded session has to behave like a real trading day.

These are not decoration. The Open Interest scrubber is built and demonstrated
against this data, so if the generator produces a flat or incoherent day the
feature looks broken for reasons that have nothing to do with the feature.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from chartnexus.infrastructure.ingestion.synthetic_session import build_synthetic_session
from chartnexus.shared_kernel.domain.errors import ValidationError

_IST = timezone(timedelta(hours=5, minutes=30))
_DATE = date(2026, 8, 5)


@pytest.fixture(scope="module")
def session() -> list:
    return build_synthetic_session(symbol="NIFTY", session_date=_DATE)


def _ist(moment: datetime) -> datetime:
    return moment.astimezone(_IST)


def _peak(snapshot, option_type: str) -> Decimal:
    legs = [row for row in snapshot.rows if row.option_type == option_type]
    return max(legs, key=lambda row: row.oi).strike


def _centre_of_mass(snapshot, option_type: str) -> float:
    """OI-weighted mean strike — where the bulk of the interest sits."""
    legs = [row for row in snapshot.rows if row.option_type == option_type]
    total = sum(row.oi for row in legs)
    return sum(float(row.strike) * row.oi for row in legs) / total


def _step(snapshot) -> float:
    strikes = sorted({float(row.strike) for row in snapshot.rows})
    return strikes[1] - strikes[0]


# -- shape ------------------------------------------------------------------


def test_covers_the_session_at_the_ingest_cadence(session: list) -> None:
    # 09:15 to 15:30 inclusive at 180s = 126 frames. The scrubber needs a dense
    # timeline; two frames is the starved state this exists to fix.
    assert len(session) == 126
    assert _ist(session[0].captured_at).time() == time(9, 15)
    assert _ist(session[-1].captured_at).time() == time(15, 30)
    assert all(snap.captured_at.tzinfo is not None for snap in session)
    assert session[0].captured_at.utcoffset() == UTC.utcoffset(None)


def test_timestamps_are_strictly_increasing(session: list) -> None:
    stamps = [snap.captured_at for snap in session]
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps)


def test_the_ladder_is_fixed_for_the_whole_session(session: list) -> None:
    # A real exchange does not add and drop strikes every three minutes, and a
    # ladder that shifted would make every frame's totals incomparable.
    ladders = {frozenset(row.strike for row in snap.rows) for snap in session}
    assert len(ladders) == 1
    assert len(next(iter(ladders))) == 41  # ATM +- 20 steps


def test_every_strike_is_quoted_on_both_sides(session: list) -> None:
    for snap in (session[0], session[63], session[-1]):
        calls = {row.strike for row in snap.rows if row.option_type == "CE"}
        puts = {row.strike for row in snap.rows if row.option_type == "PE"}
        assert calls == puts


def test_headers_are_populated(session: list) -> None:
    for snap in (session[0], session[-1]):
        assert snap.source == "mock"
        assert snap.session_date == _DATE
        assert snap.atm_strike is not None
        assert snap.max_pain_strike is not None
        assert snap.pcr_oi is not None
        assert snap.total_call_oi and snap.total_put_oi
        assert snap.lot_size == 75


# -- row invariants ---------------------------------------------------------


def test_open_interest_is_never_negative(session: list) -> None:
    assert min(row.oi for snap in session for row in snap.rows) >= 0


def test_oi_change_is_the_day_change(session: list) -> None:
    # The single-snapshot tier reconstructs the session open by subtracting this
    # field. Storing anything other than oi(t) - oi(open) silently corrupts it.
    opening = {(row.strike, row.option_type): row.oi for row in session[0].rows}
    for snap in session:
        for row in snap.rows:
            assert row.oi_change == row.oi - opening[(row.strike, row.option_type)]


def test_the_first_frame_has_no_day_change(session: list) -> None:
    assert all(row.oi_change == 0 for row in session[0].rows)


def test_implied_volatility_is_always_present(session: list) -> None:
    # Keeping IV available across the archive is half the reason it exists.
    assert all(row.iv is not None for snap in session for row in snap.rows)
    assert all(row.ltp is not None for snap in session for row in snap.rows)


# -- the day actually happens -----------------------------------------------


def test_interest_builds_through_the_day(session: list) -> None:
    assert session[-1].total_call_oi >= session[0].total_call_oi * 1.3
    assert session[-1].total_put_oi >= session[0].total_put_oi * 1.3


def test_some_strikes_unwind(session: list) -> None:
    # Writers cover where spot has travelled through a strike. Without any
    # decrease the chart's "OI decrease" legend swatches would never be used.
    assert any(row.oi_change < 0 for row in session[-1].rows)


def test_the_open_interest_profile_travels_with_spot(session: list) -> None:
    """The chart must *change shape* when scrubbed, not merely grow taller.

    Measured as the OI-weighted mean strike rather than the argmax: round
    strikes attract enough extra interest that the tallest bar tends to stay put
    on one of them all session — which is what real chains do too — while the
    distribution around it still migrates.

    Summed across both sides rather than asserted per side. On an ordinary
    0.6% day one side can genuinely sit still while the other carries the move,
    and which one that is depends on the seed; requiring both to travel would be
    asserting something the model does not claim.
    """
    step = _step(session[0])

    drift = sum(
        abs(_centre_of_mass(session[-1], side) - _centre_of_mass(session[0], side))
        for side in ("CE", "PE")
    )

    assert drift > step * 0.5, f"interest barely moved: {drift:.1f}"


def test_the_change_profile_deepens_through_the_day(session: list) -> None:
    # What the chart's default mode ("OI Change+Total") actually draws. This is
    # the reliable "scrubbing changes the picture" property: the change bars
    # start at nothing and end substantial, whatever spot did.
    early = max(abs(row.oi_change) for row in session[10].rows)
    late = max(abs(row.oi_change) for row in session[-1].rows)

    assert late > early * 3


def test_calls_are_written_above_spot_and_puts_below(session: list) -> None:
    """The shape that makes a chain read as a chain.

    Centring both sides on ATM stacks a call and a put of near-equal height on
    every strike, which looks like noise. Real chains split: calls out to the
    upside as resistance, puts below as support.
    """
    last = session[-1]
    spot = float(last.spot)
    calls = {float(row.strike): row.oi for row in last.rows if row.option_type == "CE"}
    puts = {float(row.strike): row.oi for row in last.rows if row.option_type == "PE"}
    step = _step(last)

    above = spot + 6 * step
    below = spot - 6 * step
    nearest = min(calls, key=lambda strike: abs(strike - above))
    lowest = min(calls, key=lambda strike: abs(strike - below))

    assert calls[nearest] > puts[nearest], "calls should dominate above spot"
    assert puts[lowest] > calls[lowest], "puts should dominate below spot"


def test_the_peak_sits_on_a_round_strike(session: list) -> None:
    # Real chains cluster interest on round numbers; a smooth bell curve reads
    # as fake at a glance.
    assert _peak(session[-1], "CE") % 100 == 0
    assert _peak(session[-1], "PE") % 100 == 0


def test_neighbouring_strikes_are_not_uniform(session: list) -> None:
    # A round strike must visibly outrank the ones either side of it.
    by_strike = {float(row.strike): row.oi for row in session[-1].rows if row.option_type == "CE"}
    step = _step(session[-1])
    rounds = [s for s in by_strike if s % 500 == 0 and s - step in by_strike]

    assert rounds, "the ladder should span at least one 500-point strike"
    for strike in rounds:
        assert by_strike[strike] > by_strike[strike - step]


def test_spot_moves_but_stays_plausible(session: list) -> None:
    spots = [float(snap.spot) for snap in session]
    assert len(set(spots)) > 100
    swing = (max(spots) - min(spots)) / spots[0]
    assert 0.002 < swing < 0.04


def test_header_metrics_track_the_day(session: list) -> None:
    # Per-frame headers are what let the spot line, ATM band and max-pain marker
    # follow the scrubber instead of staying pinned to the newest snapshot.
    assert len({snap.atm_strike for snap in session}) > 1
    assert len({snap.max_pain_strike for snap in session}) > 1


# -- determinism ------------------------------------------------------------


def test_re_seeding_is_byte_identical(session: list) -> None:
    # What makes `--replace` safe and lets these assertions be exact.
    assert build_synthetic_session(symbol="NIFTY", session_date=_DATE) == session


def test_different_days_differ(session: list) -> None:
    other = build_synthetic_session(symbol="NIFTY", session_date=date(2026, 8, 4))
    assert [snap.spot for snap in other] != [snap.spot for snap in session]


@pytest.mark.parametrize(
    ("symbol", "lot", "step"),
    [("NIFTY", 75, 50), ("BANKNIFTY", 30, 100), ("SENSEX", 20, 100)],
)
def test_each_instrument_uses_its_own_ladder(symbol: str, lot: int, step: int) -> None:
    session = build_synthetic_session(symbol=symbol, session_date=_DATE)
    strikes = sorted({row.strike for row in session[0].rows})
    assert session[0].lot_size == lot
    assert strikes[1] - strikes[0] == Decimal(step)


# -- edges ------------------------------------------------------------------


def test_a_custom_window_is_honoured() -> None:
    session = build_synthetic_session(
        symbol="NIFTY",
        session_date=_DATE,
        interval_seconds=900,
        start=time(9, 15),
        end=time(10, 15),
    )
    assert len(session) == 5
    assert _ist(session[-1].captured_at).time() == time(10, 15)


def test_an_inverted_window_produces_nothing() -> None:
    assert (
        build_synthetic_session(
            symbol="NIFTY", session_date=_DATE, start=time(15, 30), end=time(9, 15)
        )
        == []
    )


def test_a_non_positive_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="interval_seconds"):
        build_synthetic_session(symbol="NIFTY", session_date=_DATE, interval_seconds=0)


def test_an_unknown_symbol_is_rejected() -> None:
    with pytest.raises(ValidationError, match="not a tradeable instrument"):
        build_synthetic_session(symbol="DOGECOIN", session_date=_DATE)


# -- truncation -------------------------------------------------------------


def test_until_stops_the_session_at_that_instant(session: list) -> None:
    # Seeding today at 11:55 must not claim a 15:30 capture. An archive that
    # does pins the tool's "as of" handle to 3:30 pm all morning.
    noon = datetime(2026, 8, 5, 6, 30, tzinfo=UTC)  # 12:00 IST

    partial = build_synthetic_session(symbol="NIFTY", session_date=_DATE, until=noon)

    assert partial
    assert len(partial) < len(session)
    assert partial[-1].captured_at <= noon
    # 09:15 + 55 steps of 3 minutes lands exactly on the cutoff, which is kept.
    assert _ist(partial[-1].captured_at).time() == time(12, 0)


def test_truncation_only_removes_the_tail(session: list) -> None:
    # What makes re-seeding later in the day safe: the frames already written
    # come back byte-identical, so `--replace` extends history instead of
    # rewriting it. Generating the day in full and slicing is what buys this —
    # deriving the shape from a short day would move every earlier value.
    noon = datetime(2026, 8, 5, 6, 30, tzinfo=UTC)

    partial = build_synthetic_session(symbol="NIFTY", session_date=_DATE, until=noon)

    assert partial == session[: len(partial)]


def test_an_instant_before_the_open_yields_nothing() -> None:
    dawn = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)  # 07:30 IST

    assert build_synthetic_session(symbol="NIFTY", session_date=_DATE, until=dawn) == []


def test_an_instant_after_the_close_keeps_the_whole_day(session: list) -> None:
    midnight = datetime(2026, 8, 5, 20, 0, tzinfo=UTC)

    assert build_synthetic_session(symbol="NIFTY", session_date=_DATE, until=midnight) == session
