"""What a skill is handed to reason over.

``MarketSnapshot`` is the flattened, adapter-free view of everything the four
skills need: OI/PCR figures, the gamma profile's headline levels, an IV read,
and a short candle history for trend and ATR. The infrastructure bridge
(:mod:`marketcompass.infrastructure.analytics.guidance_market_source`) assembles
it from ``options_analytics`` and ``market_data``; the domain never sees those
types, only these plain numbers.

Every market-derived field is ``Optional``: a skill with no usable input scores
``None`` and drops out of the vote rather than voting neutral. ``sources`` holds
the provenance of each leg that actually contributed, so the guidance can report
the worst of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from marketcompass.contexts.signals.domain.models import Provenance


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """A single instant of one instrument, as the skills read it."""

    symbol: str
    spot: float

    # -- OI / PCR (from options_analytics GetOiView) -------------------------
    atm_strike: float | None = None
    lot_size: int | None = None
    expiry_date: str | None = None
    pcr: float | None = None
    pcr_change: float | None = None
    total_call_oi_chg: int | None = None
    total_put_oi_chg: int | None = None
    max_pain: float | None = None
    #: 0-100 bullish read from the OI view's aggregate sentiment, if present.
    bullish_pct: int | None = None

    # -- Dealer positioning (from options_analytics GetGex, latest frame) -----
    gex_net: float | None = None
    call_wall: float | None = None
    put_wall: float | None = None
    gamma_flip: float | None = None
    net_cross: float | None = None
    #: Fraction of legs (0-1) that carried a quoted IV. Low coverage means the
    #: gamma read is thin and the OI skill should lean on it less.
    iv_coverage: float | None = None

    # -- Volatility (from market_data option chain) --------------------------
    iv_percentile: float | None = None
    atm_call_iv: float | None = None
    atm_put_iv: float | None = None

    # -- Price action (from market_data history, oldest bar first) -----------
    closes: tuple[float, ...] = ()
    highs: tuple[float, ...] = ()
    lows: tuple[float, ...] = ()

    #: Listed strikes, ascending — lets Level-Based snap to tradeable prices.
    strikes: tuple[float, ...] = ()

    #: Provenance of every leg that fed this snapshot. The guidance reports the
    #: worst; an empty tuple is treated as MOCK (nothing real contributed).
    sources: tuple[Provenance, ...] = field(default_factory=tuple)

    @property
    def provenance(self) -> Provenance:
        return Provenance.worst(list(self.sources))
