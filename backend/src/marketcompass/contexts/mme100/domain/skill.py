"""MME100's single skill: disciplined Indian pre-market analysis.

Adapted from the ``indian-stock-market-analysis`` skill: a brokerage-research-desk
framework that always answers in six sections — global cues, India outlook, key
sectors, stocks to watch, events, and risks. Unlike HELLA's planner-routed skill
registry, MME100 has exactly one skill and folds the whole framework into the
system prompt every analytical turn.

Pure domain. The tool-name constants are the same strings the infrastructure
tools register under; MME100 declares its own copy so it never imports copilot.
``WEB_SEARCH`` is not a client-side tool — it is Anthropic's server-side web
search, bound to the model in ``infrastructure`` — but its name lives here so the
UI tool chips and the allow-list share one source of truth.
"""

from __future__ import annotations

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

#: Anthropic's server-side web search (bound to the model in infrastructure). Not
#: a client-side StructuredTool — the name is here only so the UI and the
#: allow-list agree on it.
WEB_SEARCH = "web_search"

# The India read-only surface MME100 grounds its domestic read in. Global cues
# (US markets, GIFT Nifty, crude, USD-INR, yields) come from WEB_SEARCH, since the
# broker tools cover only NSE/BSE indices.
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

# The six analysis sections, surfaced as chips so the UI shows the framework
# MME100 reasons through (the analogue of STRYX's playbook chips).
SECTION_TITLES: tuple[str, ...] = (
    "Global Cues",
    "India Outlook",
    "Key Sectors",
    "Stocks to Watch",
    "Key Events",
    "Risk Factors",
)


def titles() -> tuple[str, ...]:
    return SECTION_TITLES


# The framework, folded into the analytical system prompt. Kept tight: the model
# already knows how to analyse; this fixes the *structure*, the *discipline*, and
# the *sources* so every answer reads like the same research desk.
INSTRUCTIONS = (
    "Structure every market-analysis answer as these six sections, in order, with "
    "concrete numbers — never vague statements:\n"
    "1. GLOBAL CUES — US markets (Dow/S&P/Nasdaq), Asian markets, crude, gold, "
    "USD-INR, US 10Y & India 10Y yields. These are NOT in your broker tools: use "
    "web search for the latest figures, and cite the level and direction. If a "
    "figure can't be fetched, say so rather than inventing it.\n"
    "2. INDIA OUTLOOK — GIFT Nifty level and its premium/discount to spot (web "
    "search), the expected opening gap, the overall bias, and concrete Nifty 50 "
    "(and Bank Nifty when relevant) support/resistance levels grounded in your "
    "spot/OHLC/OI tools.\n"
    "3. KEY SECTORS — 4-6 sectors, each BULLISH/BEARISH/NEUTRAL with a one-line "
    "driver and representative stocks.\n"
    "4. STOCKS TO WATCH — 3-6 names, each with the catalyst, support 1/2, "
    "resistance 1/2, a bias with timeframe, and a stop-loss / risk note.\n"
    "5. KEY EVENTS — scheduled domestic and global data/events that could move the "
    "tape today (web search for the day's calendar).\n"
    "6. RISK FACTORS — volatility triggers, global and domestic risks, and a "
    "balanced closing risk statement.\n\n"
    "Ground every India number in a tool result from THIS turn; ground every "
    "global number in a web-search result from this turn. If the data source is "
    "'mock' (simulated), say so and treat the read as illustrative. Use measured, "
    "probabilistic language ('likely', 'if X then Y', 'risk-reward favours') — "
    "never guarantees ('will', 'definitely'), hype, or FOMO. Always state stop "
    "losses for stock ideas. The trader is looking at one instrument; centre the "
    "India Outlook on it unless they name another."
)
