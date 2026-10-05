"""OI Analysis skill — the heaviest directional vote.

Reads the options book three ways and blends them into one score:

* **PCR** relative to the 0.7-1.5 band. A high put/call ratio is put-heavy —
  writers selling puts, a bullish tell; a low one is call-heavy and bearish.
  The reading is contrarian at the extremes, which is why the band matters.
* **Build-up near the money** — whether today's OI change is stacking on the put
  side (support building, bullish) or the call side (resistance building,
  bearish).
* **Dealer gamma** — the sign of net GEX and where the gamma flip sits relative
  to spot: above the flip dealers dampen moves (mean-reverting), below it they
  amplify (trending). Thin IV coverage discounts this leg.

Weight 3.0 — it folds three of the four legs the design doc listed (OI/PCR, GEX,
IV) into a single skill, matching how a desk actually reads the chain.
"""

from __future__ import annotations

from chartnexus.contexts.signals.domain.indicators import clamp
from chartnexus.contexts.signals.domain.inputs import MarketSnapshot
from chartnexus.contexts.signals.domain.models import SkillRead

WEIGHT = 3.0
_LABEL = "OI Analysis"
_SKILL = "oi_analysis"

# PCR band: inside it the book is balanced and OI says little. Outside it the
# read is contrarian — very put-heavy is bullish, very call-heavy bearish.
_PCR_LOW = 0.7
_PCR_HIGH = 1.5

# Score magnitude past which a read is called bullish/bearish rather than neutral.
_LEAN = 0.15


def analyse(snap: MarketSnapshot) -> SkillRead:
    parts: list[float] = []
    details: list[str] = []

    pcr_score = _score_pcr(snap.pcr, details)
    if pcr_score is not None:
        parts.append(pcr_score)

    buildup_score = _score_buildup(snap.total_call_oi_chg, snap.total_put_oi_chg, details)
    if buildup_score is not None:
        parts.append(buildup_score)

    gamma_score = _score_gamma(snap, details)
    if gamma_score is not None:
        parts.append(gamma_score)

    if not parts:
        return SkillRead(
            skill=_SKILL,
            label=_LABEL,
            weight=WEIGHT,
            score=None,
            headline="No options positioning data this session.",
            details=(),
        )

    score = clamp(sum(parts) / len(parts))
    return SkillRead(
        skill=_SKILL,
        label=_LABEL,
        weight=WEIGHT,
        score=score,
        headline=_headline(score, snap.pcr),
        details=tuple(details),
    )


def _score_pcr(pcr: float | None, details: list[str]) -> float | None:
    if pcr is None or pcr <= 0.0:
        return None
    if pcr >= _PCR_HIGH:
        # Put-heavy — bullish, saturating as it climbs past the band.
        score = clamp((pcr - _PCR_HIGH) / _PCR_HIGH + 0.3)
        details.append(f"PCR {pcr:.2f} — put-heavy, bullish positioning.")
        return score
    if pcr <= _PCR_LOW:
        score = clamp(-((_PCR_LOW - pcr) / _PCR_LOW) - 0.3)
        details.append(f"PCR {pcr:.2f} — call-heavy, bearish positioning.")
        return score
    # Inside the band: a gentle lean toward whichever edge it is nearer.
    midpoint = (_PCR_LOW + _PCR_HIGH) / 2.0
    score = clamp((pcr - midpoint) / (_PCR_HIGH - _PCR_LOW))
    details.append(f"PCR {pcr:.2f} — balanced book.")
    return score


def _score_buildup(call_chg: int | None, put_chg: int | None, details: list[str]) -> float | None:
    if call_chg is None or put_chg is None:
        return None
    total = abs(call_chg) + abs(put_chg)
    if total == 0:
        return None
    # Puts building (positive put_chg) is bullish; calls building is bearish.
    score = clamp((put_chg - call_chg) / total)
    if put_chg > call_chg:
        details.append("OI building on the put side — support forming below.")
    elif call_chg > put_chg:
        details.append("OI building on the call side — resistance forming above.")
    return score


def _score_gamma(snap: MarketSnapshot, details: list[str]) -> float | None:
    if snap.gex_net is None:
        return None
    coverage = snap.iv_coverage if snap.iv_coverage is not None else 0.0
    if coverage <= 0.0:
        return None

    # Flip vs spot: below the flip dealers amplify (trend-friendly), above it
    # they dampen. Combined with net sign it gives a directional lean.
    lean = 0.0
    if snap.gamma_flip is not None and snap.spot > 0.0:
        if snap.spot < snap.gamma_flip:
            lean = -0.3  # below flip: downside moves get amplified
            details.append(f"Spot below gamma flip {snap.gamma_flip:,.0f} — moves amplified.")
        else:
            lean = 0.2  # above flip: dealers cushion, mild bullish stability
            details.append(f"Spot above gamma flip {snap.gamma_flip:,.0f} — dealers dampen.")

    net_sign = 1.0 if snap.gex_net > 0 else -1.0 if snap.gex_net < 0 else 0.0
    score = clamp((0.3 * net_sign + lean) * coverage)
    return score


def _headline(score: float, pcr: float | None) -> str:
    lean = "bullish" if score > _LEAN else "bearish" if score < -_LEAN else "neutral"
    pcr_txt = f"PCR {pcr:.2f}" if pcr else "options"
    return f"{pcr_txt} positioning reads {lean}."
