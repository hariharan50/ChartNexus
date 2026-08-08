"""Derive an illustrative entry/stop/target from levels and ATR.

Pure geometry over the level map. Nothing here is an order — the app places no
trades — so the output is labelled illustrative and the suggested contract is a
display string, not a broker symbol. Built only for a directional call; a HOLD
has no scaffold.
"""

from __future__ import annotations

from marketcompass.contexts.signals.domain.inputs import MarketSnapshot
from marketcompass.contexts.signals.domain.models import Decision, Levels, TradeScaffold


def build_scaffold(
    decision: Decision,
    snap: MarketSnapshot,
    levels: Levels,
    atr_value: float | None,
) -> TradeScaffold:
    """Entry at spot, stop at the opposing wall (or 1x ATR), target at the next wall."""
    if decision is Decision.HOLD:
        return TradeScaffold()

    entry = snap.spot
    long = decision is Decision.BUY

    stop = _stop(entry, levels, atr_value, long=long)
    target = _target(entry, levels, snap.max_pain, long=long)
    risk_reward = _risk_reward(entry, stop, target)
    contract = _suggest_contract(snap, long=long)

    return TradeScaffold(
        entry=round(entry, 2),
        stop=None if stop is None else round(stop, 2),
        target=None if target is None else round(target, 2),
        risk_reward=None if risk_reward is None else round(risk_reward, 2),
        suggested_contract=contract,
    )


def _stop(entry: float, levels: Levels, atr_value: float | None, *, long: bool) -> float | None:
    # The wall the trade would be stopped against, or one ATR, whichever is
    # tighter — a stop wider than the structure it is protecting is not a stop.
    wall = levels.support if long else levels.resistance
    candidates: list[float] = []
    if wall is not None and ((long and wall < entry) or (not long and wall > entry)):
        candidates.append(wall)
    if atr_value is not None and atr_value > 0.0:
        candidates.append(entry - atr_value if long else entry + atr_value)
    if not candidates:
        return None
    # Tighter = closest to entry.
    return min(candidates, key=lambda level: abs(entry - level))


def _target(entry: float, levels: Levels, max_pain: float | None, *, long: bool) -> float | None:
    wall = levels.resistance if long else levels.support
    candidates: list[float] = []
    if wall is not None and ((long and wall > entry) or (not long and wall < entry)):
        candidates.append(wall)
    if max_pain is not None and ((long and max_pain > entry) or (not long and max_pain < entry)):
        candidates.append(max_pain)
    if not candidates:
        return None
    # The nearer objective — the first level price would actually reach.
    return min(candidates, key=lambda level: abs(entry - level))


def _risk_reward(entry: float, stop: float | None, target: float | None) -> float | None:
    if stop is None or target is None:
        return None
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk <= 0.0:
        return None
    return reward / risk


def _suggest_contract(snap: MarketSnapshot, *, long: bool) -> str | None:
    if snap.atm_strike is None:
        return None
    side = "CE" if long else "PE"
    strike = round(snap.atm_strike)
    expiry = f" {snap.expiry_date}" if snap.expiry_date else ""
    return f"{snap.symbol} {strike}{side}{expiry} (nearest ATM, illustrative)"
