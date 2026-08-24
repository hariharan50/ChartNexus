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
    "Deliver a DETAILED, brokerage-desk pre-market analysis structured as these six "
    "sections, in order, each with a bold heading. Be specific and quantitative in "
    "every section — cite levels, percentages, and directions, never vague "
    "statements. Aim for depth: this is a full research note, not a summary.\n\n"
    "1. GLOBAL CUES — this section must be thorough; it drives the day's tone. Cover "
    "EACH of the following on its own line, with the latest figure, the overnight "
    "move (points and %), the key driver, and the read-through for Indian equities:\n"
    "   - US markets: Dow, S&P 500 and Nasdaq — closing level, % change, and what "
    "moved them (earnings, econ data, Fed).\n"
    "   - Asian markets: Nikkei, Hang Seng, Shanghai, Kospi — current direction and "
    "regional tone.\n"
    "   - Crude oil (Brent/WTI): level and trend, and its impact on OMCs, paints, "
    "aviation and inflation.\n"
    "   - Gold: level and safe-haven read.\n"
    "   - USD-INR: rate and direction, and the read for IT exporters vs importers.\n"
    "   - US 10Y Treasury and India 10Y G-Sec yields: levels and what they say about "
    "global risk appetite and domestic borrowing costs.\n"
    "   - Overall global sentiment: one line synthesising risk-on / risk-off.\n"
    "   These are NOT in your broker tools — use web search for every figure, cite "
    "the level and direction, and if any figure can't be fetched say so rather than "
    "inventing it.\n"
    "2. INDIA OUTLOOK — GIFT Nifty level and its premium/discount to spot (web "
    "search); the expected opening gap in points and %; whether it reads as gap-up "
    "(>0.5%), gap-down (<-0.5%) or flat; the overall bias (bullish/bearish/sideways) "
    "with the reasoning; and concrete key levels grounded in your spot/OHLC/OI "
    "tools — immediate & strong support, immediate & strong resistance for Nifty 50, "
    "plus Bank Nifty levels and sectoral bias when relevant.\n"
    "3. KEY SECTORS — 4-6 sectors, each labelled BULLISH/BEARISH/NEUTRAL with a "
    "specific driver (rate cycle, USFDA, dollar move, crude, results) and 2-3 "
    "representative stocks per sector.\n"
    "4. STOCKS TO WATCH — 4-6 names. For each: the catalyst (earnings, breakout, "
    "sector strength) with specifics; support 1 & support 2; resistance 1 & "
    "resistance 2; a bias with a timeframe; and a risk note with the stop-loss "
    "level and position-sizing advice.\n"
    "5. KEY EVENTS — scheduled domestic (RBI, CPI/IIP/GDP/PMI, FII/DII flows, "
    "results) and global (Fed, US data, central banks, geopolitics) events that "
    "could move the tape today; web search the day's calendar.\n"
    "6. RISK FACTORS — volatility triggers (VIX, PCR, event risk), global risks, "
    "domestic risks, and a balanced closing risk statement reminding the trader to "
    "use strict stop losses and avoid overleveraging.\n\n"
    "Ground every India number in a tool result from THIS turn; ground every "
    "global number in a web-search result from this turn. If the data source is "
    "'mock' (simulated), say so and treat the read as illustrative. Use measured, "
    "probabilistic language ('likely', 'if X then Y', 'risk-reward favours') — "
    "never guarantees ('will', 'definitely'), hype, or FOMO. Always state stop "
    "losses for stock ideas. The trader is looking at one instrument; centre the "
    "India Outlook on it unless they name another."
)
