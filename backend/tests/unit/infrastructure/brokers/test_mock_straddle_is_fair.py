"""The synthetic book must price an at-the-money straddle fairly.

Two properties, both of which the mock got wrong and neither of which any other
test would have caught — they are invisible in a single chain and only show up
once something *holds a position* across captures.

**Delta-neutral at the money.** A straddle is the one structure whose value is
flat in the underlying at the strike: the call's delta and the put's cancel. If
the synthetic curve has any slope there, a held straddle gains or loses on
direction alone, and every tool that replays one inherits a drift that looks
like a market move but is an artefact of the generator.

**Theta equals gamma.** A book where decay outruns curvature pays a premium
seller for free, and one where it lags pays the buyer. Either way a strategy
page built on it reports an edge the market never offered. Selling the
at-the-money straddle and re-striking as the market moves is the sharpest probe
of that balance, so that is what this asserts — across several sessions, because
one session is a coin toss.
"""

from __future__ import annotations

from datetime import date

import pytest

from chartnexus.contexts.options_analytics.domain.oi_math import ChainRow
from chartnexus.contexts.options_analytics.domain.straddle_pnl import PnlFrame, simulate
from chartnexus.infrastructure.brokers.mock.session_model import session_frames

pytestmark = pytest.mark.unit

#: The shared catalog's NIFTY, not a universe of this module's own — installing
#: one globally replaces the session fixture for every test that runs after.
LOT_SIZE = 75
STEP = 50.0

SESSIONS = [date(2026, 10, day) for day in (1, 2, 5, 6, 7, 8)]


def frames_for(session: date) -> list[PnlFrame]:
    return [
        PnlFrame(
            session=session.isoformat(),
            timestamp=frame.captured_at.isoformat(),
            spot=frame.spot,
            rows=tuple(
                ChainRow(
                    strike=leg.strike,
                    option_type=leg.option_type,
                    oi=leg.oi,
                    oi_change=leg.oi_change,
                    ltp=leg.ltp,
                    volume=leg.volume,
                )
                for leg in frame.legs
            ),
        )
        for frame in session_frames("NIFTY", session, interval_seconds=60)
    ]


def straddle_at(frame: PnlFrame, strike: float) -> float:
    legs = [row.ltp for row in frame.rows if row.strike == strike]
    assert len(legs) == 2, f"no two-sided quote at {strike}"
    return sum(legs)


class TestTheStraddleIsFlatAtTheMoney:
    """The defining property: a straddle's value bottoms out at the strike."""

    def test_the_cheapest_straddle_is_the_one_at_the_money(self) -> None:
        frame = frames_for(SESSIONS[0])[0]
        strikes = sorted({row.strike for row in frame.rows})
        atm = min(strikes, key=lambda k: abs(k - frame.spot))

        cheapest = min(strikes, key=lambda k: straddle_at(frame, k))
        assert cheapest == atm

    def test_it_costs_more_the_further_the_strike_is_from_spot(self) -> None:
        frame = frames_for(SESSIONS[0])[0]
        strikes = sorted({row.strike for row in frame.rows})
        atm = min(strikes, key=lambda k: abs(k - frame.spot))

        above = [k for k in strikes if k > atm][:6]
        values = [straddle_at(frame, k) for k in above]
        assert values == sorted(values), "the curve must rise away from the money"

    def test_one_strike_away_costs_barely_more_than_at_the_money(self) -> None:
        """The near-flat zone. A first-order slope here is the bug this catches.

        The old curve rose 0.51 points for every point of distance, so one
        50-point strike cost ~26 points more — a 9% jump in premium for moving
        one strike, which no real chain shows.
        """
        frame = frames_for(SESSIONS[0])[0]
        strikes = sorted({row.strike for row in frame.rows})
        atm = min(strikes, key=lambda k: abs(k - frame.spot))
        neighbour = min((k for k in strikes if k > atm), default=atm)

        at_money = straddle_at(frame, atm)
        one_away = straddle_at(frame, neighbour)
        assert (one_away - at_money) / at_money < 0.05


class TestSellingItIsNotFreeMoney:
    """Theta collected must be paid for in gamma, or the book prints money."""

    def results(self) -> list[float]:
        return [
            simulate(
                frames_for(session),
                adjustment_points=STEP,
                lot_size=LOT_SIZE,
                lots=1,
                strike_step=STEP,
            ).total_pnl
            for session in SESSIONS
        ]

    def test_the_average_session_roughly_breaks_even(self) -> None:
        """Fair pricing, stated as a number.

        The bound is loose because six seeded sessions are a small sample; it is
        tight enough to catch the failure that mattered, which was +8,421 a lot.
        """
        outcomes = self.results()
        mean = sum(outcomes) / len(outcomes)
        assert abs(mean) < 600, f"mean P&L {mean:,.0f} — the book is not fair"

    def test_the_seller_neither_always_wins_nor_always_loses(self) -> None:
        outcomes = self.results()
        assert any(value > 0 for value in outcomes), "no winning session"
        assert any(value < 0 for value in outcomes), "no losing session"

    def test_a_session_moves_enough_to_be_worth_simulating(self) -> None:
        """Guards the opposite failure: a book so flat nothing ever happens."""
        outcomes = self.results()
        assert max(abs(value) for value in outcomes) > 100


class TestThePremiumIsRealistic:
    def test_the_at_the_money_straddle_is_priced_like_the_real_contract(self) -> None:
        """~194 points on NIFTY, which is what the live chain quoted."""
        frame = frames_for(SESSIONS[0])[0]
        strikes = sorted({row.strike for row in frame.rows})
        atm = min(strikes, key=lambda k: abs(k - frame.spot))
        assert 150.0 < straddle_at(frame, atm) < 250.0

    def test_premium_decays_visibly_across_the_session(self) -> None:
        """Straddle Chart exists to show this, so it must be worth drawing."""
        frames = frames_for(SESSIONS[0])
        first, last = frames[0], frames[-1]

        def at_money(frame: PnlFrame) -> float:
            strikes = sorted({row.strike for row in frame.rows})
            return straddle_at(frame, min(strikes, key=lambda k: abs(k - frame.spot)))

        assert at_money(last) < at_money(first) * 0.9
