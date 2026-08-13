"""Forward-return labels — the ground truth the ensemble is fit and scored against.

A signal is only as good as what actually happened next. For each point in a
close series we look ``lookahead`` bars ahead and label the move **up** (1) or
**down** (0); a move inside a small dead-band is *flat* and returns ``None`` so it
drops out of training rather than teaching the model noise. The lookahead differs
per horizon — a few bars for intraday, a daily-bar count for swing — so the caller
passes the right series and horizon for the label it wants.

Pure: numbers in, an integer label (or ``None``) out. No I/O, no framework.
"""

from __future__ import annotations

# A move smaller than this fraction is treated as flat (no directional label).
DEFAULT_DEADBAND = 0.0005  # 5 bps


def forward_return(closes: tuple[float, ...], i: int, lookahead: int) -> float | None:
    """Return over ``[i, i + lookahead]`` as a fraction, or ``None`` if out of range."""
    j = i + lookahead
    if lookahead <= 0 or i < 0 or j >= len(closes):
        return None
    base = closes[i]
    if base <= 0:
        return None
    return closes[j] / base - 1.0


def label_at(
    closes: tuple[float, ...],
    i: int,
    lookahead: int,
    *,
    deadband: float = DEFAULT_DEADBAND,
) -> int | None:
    """Binary up/down label for the move after bar ``i``.

    ``1`` when the forward return clears ``+deadband``, ``0`` when it clears
    ``-deadband``, ``None`` when flat within the band or the window runs off the
    end (undated points must not be counted).
    """
    fwd = forward_return(closes, i, lookahead)
    if fwd is None:
        return None
    if fwd > deadband:
        return 1
    if fwd < -deadband:
        return 0
    return None
