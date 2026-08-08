"""The whole pure pipeline: a snapshot in, a Guidance out.

Covers the invariants the design doc calls non-negotiable — a mock leg makes the
whole call illustrative and floors its confidence — alongside the happy path
(aligned skills produce a directional call with a coherent scaffold) and the
empty case (no data is HOLD with no scaffold, never a confident guess).
"""

from __future__ import annotations

from marketcompass.contexts.signals.domain.guider import build_guidance
from marketcompass.contexts.signals.domain.inputs import MarketSnapshot
from marketcompass.contexts.signals.domain.models import Decision, Provenance


def _rising(n: int, start: float, step: float) -> tuple[float, ...]:
    return tuple(start + step * i for i in range(n))


def _bullish_snapshot(source: Provenance = Provenance.LIVE) -> MarketSnapshot:
    # Steady uptrend ending ~24,850: spot sits just above the put wall (near
    # support) with the call wall far above, so all three skills lean bullish.
    closes = _rising(30, 24_300.0, 19.0)
    highs = tuple(c + 15.0 for c in closes)
    lows = tuple(c - 15.0 for c in closes)
    spot = closes[-1]
    return MarketSnapshot(
        symbol="NIFTY",
        spot=spot,
        atm_strike=24_800.0,
        lot_size=50,
        expiry_date="2026-08-13",
        pcr=1.6,  # put-heavy → bullish
        pcr_change=0.2,
        total_call_oi_chg=100_000,
        total_put_oi_chg=400_000,  # puts building → support
        max_pain=24_800.0,  # essentially at spot — no location drag
        bullish_pct=70,
        gex_net=5.0,
        call_wall=25_400.0,
        put_wall=24_800.0,
        gamma_flip=24_600.0,  # spot above flip
        net_cross=24_750.0,
        iv_coverage=0.9,
        iv_percentile=45.0,
        closes=closes,
        highs=highs,
        lows=lows,
        # 200-wide strikes so no listed strike hugs spot from above and tightens
        # resistance; the nearest resistance is 25,000, well above support.
        strikes=tuple(24_000.0 + 200.0 * i for i in range(11)),
        sources=(source, source, source),
    )


def test_aligned_bullish_inputs_yield_an_actionable_buy() -> None:
    guidance = build_guidance(_bullish_snapshot())

    assert guidance.decision is Decision.BUY
    assert guidance.confidence > 0
    assert guidance.provenance is Provenance.LIVE
    assert guidance.is_actionable is True

    # Four cards: the three voters plus the risk gate.
    assert [s.skill for s in guidance.skills] == [
        "oi_analysis",
        "price_action",
        "level_based",
        "risk_management",
    ]

    scaffold = guidance.scaffold
    assert scaffold.entry is not None
    # Long trade: stop below entry, target above.
    assert scaffold.stop is not None and scaffold.stop < scaffold.entry
    assert scaffold.target is not None and scaffold.target > scaffold.entry
    assert scaffold.suggested_contract is not None
    assert "CE" in scaffold.suggested_contract


def test_a_mock_leg_downgrades_the_whole_call() -> None:
    guidance = build_guidance(_bullish_snapshot(source=Provenance.MOCK))

    # The engine still runs and still leans bullish...
    assert guidance.decision is Decision.BUY
    # ...but the call is illustrative and its confidence is floored.
    assert guidance.provenance is Provenance.MOCK
    assert guidance.is_actionable is False
    assert guidance.confidence <= 15
    assert any("simulated" in w.lower() for w in guidance.warnings)


def test_no_data_holds_with_no_scaffold() -> None:
    empty = MarketSnapshot(symbol="NIFTY", spot=25_000.0, sources=(Provenance.LIVE,))
    guidance = build_guidance(empty)

    assert guidance.decision is Decision.HOLD
    assert guidance.confidence == 0
    assert guidance.scaffold.entry is None
    assert guidance.scaffold.suggested_contract is None
