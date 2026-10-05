"""Pure straddle math for the ATM Straddle Chart tool.

No framework, no I/O — the derivations that turn option chain rows into a
straddle premium. A straddle at a strike is ``call_ltp + put_ltp``: what it
costs to be long both legs there, and the market's own read on how far the
underlying is expected to travel by expiry.

Kept beside ``vega_math`` and re-derived locally rather than pulled from another
context, matching the convention the other Options Lab domain modules follow.
"""

from __future__ import annotations

from collections.abc import Iterable

from chartnexus.contexts.options_analytics.domain.oi_math import ChainRow


def leg_ltp(rows: Iterable[ChainRow], strike: float, *, is_call: bool) -> float | None:
    """The last traded price of one leg, or ``None`` when it is not usably quoted.

    A quote of ``0.0`` is treated as no quote, not a free option: an illiquid
    leg that last printed zero would otherwise drag a straddle down to a single
    side's value, a premium the market never showed. Same guard the synthetic
    future in ``vega_math`` uses.
    """
    for row in rows:
        if row.strike != strike:
            continue
        if row.is_call is is_call and row.ltp > 0.0:
            return row.ltp
    return None


def atm_straddle(rows: Iterable[ChainRow], atm_strike: float | None) -> float | None:
    """The straddle premium at the money: ``call_ltp + put_ltp`` at ``atm_strike``.

    Returns ``None`` when the ATM is unknown or either ATM leg is missing — the
    caller then leaves a gap rather than plotting half a straddle. ``rows`` is
    iterated once per side, so it must be a re-iterable sequence, which every
    caller here passes (a snapshot's ``rows`` tuple).
    """
    if atm_strike is None:
        return None
    call = leg_ltp(rows, atm_strike, is_call=True)
    put = leg_ltp(rows, atm_strike, is_call=False)
    if call is None or put is None:
        return None
    return call + put
