"""Hella's skill registry — what she knows and which tools each skill uses.

A *skill* is a declarative bundle: when it applies, how to reason within it, and
the read-only tools it draws on. The planner picks one or more skills for a
question; the executor then runs scoped to *only* those skills' tools and
instructions. Adding a capability is a new entry here — no graph changes.

Pure domain: tool names are string constants declared here (the single source of
truth), and the infrastructure tools import them, so a rename can't silently
desync the registry from the tools.
"""

from __future__ import annotations

from dataclasses import dataclass

# -- tool names (shared with infrastructure/agent/langgraph/tools.py) --------

GET_SPOT = "get_spot"
GET_FUTURES = "get_futures"
GET_OHLC = "get_ohlc"
GET_PREVIOUS_DAY_OHLC = "get_previous_day_ohlc"
GET_OPTION_CHAIN_SUMMARY = "get_option_chain_summary"
GET_MAX_PAIN_AND_PCR = "get_max_pain_and_pcr"
GET_GAMMA_EXPOSURE = "get_gamma_exposure"
GET_MARKET_STATUS = "get_market_status"
GET_INDICATORS = "get_indicators"


@dataclass(frozen=True, slots=True)
class Skill:
    id: str
    title: str
    #: One line the planner reads to decide whether the question needs this skill.
    when_to_use: str
    #: How Hella reasons within this skill, folded into the executor's prompt.
    instructions: str
    #: The read-only tools this skill may call. Empty for a no-data skill.
    tools: tuple[str, ...]


CONVERSATIONAL_ID = "conversational"

SKILLS: tuple[Skill, ...] = (
    Skill(
        id="oi_options_flow",
        title="OI & Options Flow",
        when_to_use=(
            "open interest, options build-up/unwinding, PCR, max pain, gamma, dealer "
            "positioning, or support/resistance read off option walls"
        ),
        instructions=(
            "Read the option chain and OI: rising call OI is overhead supply "
            "(resistance), rising put OI is support; PCR above ~1 leans bullish "
            "positioning, below leans bearish; max pain is where the most option value "
            "expires worthless (a magnet into expiry); the gamma flip is where dealer "
            "hedging switches from stabilising to amplifying. Weigh change-in-OI, not "
            "just the absolute level."
        ),
        tools=(GET_OPTION_CHAIN_SUMMARY, GET_MAX_PAIN_AND_PCR, GET_GAMMA_EXPOSURE, GET_SPOT),
    ),
    Skill(
        id="price_action_technical",
        title="Price Action & Technical",
        when_to_use=(
            "trend, momentum, candles, moving averages, breakouts, or technical "
            "levels read from price history"
        ),
        instructions=(
            "Read OHLC candles for structure: higher highs/lows is an uptrend and the "
            "reverse a downtrend; note where price sits within the recent range, the "
            "session's high/low, and how today opened relative to the previous close "
            "(gap up/down). Use `get_indicators` for the momentum/trend read — RSI "
            "(above ~70 overbought, below ~30 oversold), price vs EMA20/EMA50 (above "
            "both is a strong uptrend), VWAP (above is intraday strength), and ATR for "
            "volatility. Call out obvious support/resistance from swing points."
        ),
        tools=(GET_OHLC, GET_INDICATORS, GET_PREVIOUS_DAY_OHLC, GET_SPOT, GET_FUTURES),
    ),
    Skill(
        id="levels_range",
        title="Levels & Range",
        when_to_use=(
            "the key levels for today, the expected trading band, or where support "
            "and resistance sit"
        ),
        instructions=(
            "Triangulate today's actionable band: combine swing highs/lows and the "
            "previous session's high/low/close with the option walls (heaviest call OI "
            "as resistance, heaviest put OI as support) and max pain. Give a concrete "
            "upper and lower level. `get_indicators` gives swing support/resistance, "
            "EMAs and ATR to size a sensible band."
        ),
        tools=(
            GET_OHLC,
            GET_INDICATORS,
            GET_PREVIOUS_DAY_OHLC,
            GET_OPTION_CHAIN_SUMMARY,
            GET_MAX_PAIN_AND_PCR,
        ),
    ),
    Skill(
        id="trade_setup_risk",
        title="Trade Setup & Risk",
        when_to_use=(
            "a possible setup, an entry, a stop, a target, risk-reward, or which "
            "contract to consider"
        ),
        instructions=(
            "After reading the structure and the OI, give a decisive illustrative setup: "
            "a directional bias (BUY / SELL / HOLD with conviction), a reference entry near "
            "a level, a stop beyond the nearest opposing level, a target at the next level "
            "in the trade's direction, the resulting risk-reward, and a candidate "
            "strike/contract that fits the bias. Present the numbers as illustrative — do "
            "not refuse to give a call or defer the decision back to the user."
        ),
        tools=(
            GET_SPOT,
            GET_FUTURES,
            GET_OHLC,
            GET_INDICATORS,
            GET_PREVIOUS_DAY_OHLC,
            GET_OPTION_CHAIN_SUMMARY,
            GET_MAX_PAIN_AND_PCR,
            GET_GAMMA_EXPOSURE,
        ),
    ),
    Skill(
        id="market_context",
        title="Market Context",
        when_to_use="whether the market is open, how fresh the data is, or a quick pulse",
        instructions=(
            "Establish the backdrop: is the exchange open, what is the session date, "
            "and is the data live or simulated. Give a one-line pulse from spot and "
            "futures. If the data source is mock, say the read is illustrative."
        ),
        tools=(GET_MARKET_STATUS, GET_SPOT, GET_FUTURES),
    ),
    Skill(
        id=CONVERSATIONAL_ID,
        title="Conversation",
        when_to_use="a greeting, a question about who Hella is, help, or thanks",
        instructions=(
            "Reply warmly and briefly as Hella. Do not call any tools or discuss the "
            "market unless asked."
        ),
        tools=(),
    ),
)

_BY_ID = {skill.id: skill for skill in SKILLS}

# When the planner fails or returns nothing usable, fall back to the core
# analytical read rather than guessing — broad enough to answer most questions.
DEFAULT_IDS: tuple[str, ...] = ("oi_options_flow", "price_action_technical", "levels_range")


def skill_ids() -> list[str]:
    return [skill.id for skill in SKILLS]


def valid_ids(ids: list[str]) -> list[str]:
    """Keep only known ids, in registry order, de-duplicated."""
    seen = {skill_id for skill_id in ids if skill_id in _BY_ID}
    return [skill.id for skill in SKILLS if skill.id in seen]


def tools_for(ids: list[str]) -> set[str]:
    tools: set[str] = set()
    for skill_id in ids:
        skill = _BY_ID.get(skill_id)
        if skill is not None:
            tools.update(skill.tools)
    return tools


def titles_for(ids: list[str]) -> list[str]:
    return [_BY_ID[skill_id].title for skill_id in ids if skill_id in _BY_ID]


def is_analytical(ids: list[str]) -> bool:
    """True when any selected skill is a market read (not purely conversational).

    Drives the compliance guardrail: analytical turns must carry the disclaimer;
    a greeting must not.
    """
    return any(skill_id in _BY_ID and skill_id != CONVERSATIONAL_ID for skill_id in ids)


def instructions_block(ids: list[str]) -> str:
    """The selected skills' instructions, composed for the executor's prompt."""
    parts = [f"• {_BY_ID[i].title}: {_BY_ID[i].instructions}" for i in ids if i in _BY_ID]
    return "\n".join(parts)


def planner_catalogue() -> str:
    """The skill list the planner chooses from — id and when-to-use, one per line."""
    return "\n".join(f"- {skill.id}: {skill.when_to_use}" for skill in SKILLS)
