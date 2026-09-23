"""The deterministic MarketCompass score — same inputs, same score; bands & cards."""

from __future__ import annotations

from marketcompass.contexts.report.domain.report import (
    InstrumentSummary,
    OptionsSummary,
    Stance,
    TechnicalRead,
)
from marketcompass.contexts.report.domain.scoring import compute_score


def _summary(ltp: float | None = 100.0, chg: float | None = 0.0) -> InstrumentSummary:
    return InstrumentSummary(
        symbol="NIFTY",
        ltp=ltp,
        change=chg,
        change_pct=chg,
        prev_close=100.0,
        day_open=100.0,
        day_high=101.0,
        day_low=99.0,
        week52_low=80.0,
        week52_high=120.0,
        source="live",
    )


def _tech(ema20: float | None = 100.0, rsi: float | None = 50.0) -> TechnicalRead:
    return TechnicalRead(ema20=ema20, ema50=None, rsi14=rsi, vwap=None, atr14=None)


def _opts(
    pcr: float | None = 0.9,
    ce: float | None = 1.0,
    pe: float | None = 1.0,
    vix: float | None = 15.0,
) -> OptionsSummary:
    return OptionsSummary(
        pcr=pcr,
        pcr_change=None,
        max_pain=None,
        atm_strike=None,
        total_call_oi=ce,
        total_put_oi=pe,
        gamma_flip=None,
        india_vix=vix,
    )


def test_deterministic_same_inputs_same_score() -> None:
    a = compute_score(_summary(), _tech(), _opts())
    b = compute_score(_summary(), _tech(), _opts())
    assert a.score == b.score and a.label == b.label


def test_bullish_stack_scores_high() -> None:
    score = compute_score(
        _summary(ltp=110.0, chg=1.0),  # above EMA20, strong up day
        _tech(ema20=100.0, rsi=65.0),  # momentum bull
        _opts(pcr=1.2, ce=1.0, pe=2.0, vix=11.0),  # put-heavy, calm
    )
    assert score.score > 60
    assert "Bull" in score.label


def test_bearish_stack_scores_low() -> None:
    score = compute_score(
        _summary(ltp=90.0, chg=-1.0),
        _tech(ema20=100.0, rsi=35.0),
        _opts(pcr=0.7, ce=2.0, pe=1.0, vix=22.0),
    )
    assert score.score < 40
    assert "Bear" in score.label


def test_score_is_clamped_0_100() -> None:
    score = compute_score(
        _summary(ltp=999, chg=99), _tech(ema20=1, rsi=99), _opts(pcr=9, ce=1, pe=99, vix=1)
    )
    assert 0 <= score.score <= 100


def test_missing_data_yields_fewer_signals_no_crash() -> None:
    score = compute_score(
        _summary(ltp=None, chg=None),
        TechnicalRead(ema20=None, ema50=None, rsi14=None, vwap=None, atr14=None),
        _opts(pcr=None, ce=None, pe=None, vix=None),
    )
    assert score.signals == ()
    assert score.score == 50  # neutral default with no inputs
    assert score.label == "Neutral"


def test_signal_stances_are_valid() -> None:
    score = compute_score(_summary(ltp=110, chg=0.5), _tech(105, 60), _opts(1.1, 1, 2, 12))
    assert all(sig.stance in Stance for sig in score.signals)
