"""STRYX's five entry styles — its playbook for *how* an edge gets taken.

Each style is a declarative bundle: when it applies and the concrete trigger
logic that confirms it. Unlike HELLA's planner-routed skills, STRYX weighs *all*
five on every scan (it is a fast opportunity hunter, not a topic router), so the
whole playbook is folded into the system prompt each turn and STRYX picks the one
style — if any — whose trigger the live data actually satisfies.

Pure domain. The tool-name constants are the same strings the infrastructure
tools register under; STRYX declares its own copy so it never imports copilot.
"""

from __future__ import annotations

from dataclasses import dataclass

# -- tool names (must match infrastructure/agent/langgraph/tools.py) ----------

GET_SPOT = "get_spot"
GET_FUTURES = "get_futures"
GET_OHLC = "get_ohlc"
GET_PREVIOUS_DAY_OHLC = "get_previous_day_ohlc"
GET_OPTION_CHAIN_SUMMARY = "get_option_chain_summary"
GET_MAX_PAIN_AND_PCR = "get_max_pain_and_pcr"
GET_GAMMA_EXPOSURE = "get_gamma_exposure"
GET_MARKET_STATUS = "get_market_status"
GET_INDICATORS = "get_indicators"

# STRYX reads the full read-only surface on a scan — its edge is reacting to the
# *rate of change* across these (OI unwind, PCR ticking, volume spike), so it
# wants the OI/PCR read, the price structure, and the momentum read together.
CORE_TOOLS: tuple[str, ...] = (
    GET_MARKET_STATUS,
    GET_SPOT,
    GET_FUTURES,
    GET_OHLC,
    GET_PREVIOUS_DAY_OHLC,
    GET_INDICATORS,
    GET_OPTION_CHAIN_SUMMARY,
    GET_MAX_PAIN_AND_PCR,
    GET_GAMMA_EXPOSURE,
)


@dataclass(frozen=True, slots=True)
class EntryStyle:
    id: str
    title: str
    #: When this style is in play.
    when_to_use: str
    #: The concrete, codeable trigger that must be satisfied to fire it.
    trigger: str


ENTRY_STYLES: tuple[EntryStyle, ...] = (
    EntryStyle(
        id="early",
        title="Early Entry",
        when_to_use="the first sign of a structure shift, before full confirmation",
        trigger=(
            "A CHoCH is forming AND OI is starting to unwind at the nearest wall. Fire "
            "SMALLER than a confirmed entry and flag it explicitly as 'early / higher "
            "risk'. Never the default."
        ),
    ),
    EntryStyle(
        id="breakout",
        title="Breakout Entry",
        when_to_use="price closing beyond a defined wall/level",
        trigger=(
            "Price closes beyond the wall/level WITH volume confirmation AND OI change "
            "supporting the move (shorts covering or fresh longs building in the breakout "
            "direction). Standard size, stop just inside the broken level."
        ),
    ),
    EntryStyle(
        id="momentum",
        title="Momentum Entry",
        when_to_use="a strong directional thrust already underway",
        trigger=(
            "Strong directional candle(s) with expanding range AND rising ADX/RSI thrust "
            "AND OI building aggressively on one side. Chase only within a defined "
            "max-distance-from-trigger — never chase an already-extended candle."
        ),
    ),
    EntryStyle(
        id="liquidity",
        title="Liquidity Entry",
        when_to_use="a stop-hunt sweep and sharp reclaim",
        trigger=(
            "A liquidity sweep (stop-hunt wick) followed by a sharp reclaim, ideally at a "
            "level that also lines up with an OI wall. Tightest stop of all styles, just "
            "beyond the sweep wick — highest reward-to-risk, needs the tightest invalidation."
        ),
    ),
    EntryStyle(
        id="no_retracement",
        title="No-Retracement Entry",
        when_to_use="the highest-conviction move that offers no pullback",
        trigger=(
            "Multiple inputs all agree at once — structure + OI + volume + PCR velocity — "
            "and the move gives no retest to wait for. Enter directly on trigger "
            "confirmation. This is the signature 'I don't wait' move: the RAREST style, "
            "reserved for the highest conviction, never the default."
        ),
    ),
)

_BY_ID = {style.id: style for style in ENTRY_STYLES}


def titles() -> tuple[str, ...]:
    return tuple(style.title for style in ENTRY_STYLES)


def playbook_block() -> str:
    """The five styles, id/when/trigger, folded into STRYX's system prompt."""
    return "\n".join(
        f"• {s.title} — when: {s.when_to_use}. Trigger: {s.trigger}" for s in ENTRY_STYLES
    )


def is_style(style_id: str) -> bool:
    return style_id in _BY_ID
