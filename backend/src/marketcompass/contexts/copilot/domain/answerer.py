"""Deterministic, no-LLM answers grounded in the structured guidance.

This is what makes the AI Console work with no API key. It reads the user's
intent — conversational (greeting, who she is, help, thanks) or trading (why,
stop, target, entry, levels, contract) — and answers from the ``GuidanceSnapshot``,
the same structured state a real model would be grounded in. When an LLM is
configured, its output is preferred and these answers become the guardrail; when
it isn't, they are the answer.

It cannot converse freely the way a language model can — that is what the
Anthropic/OpenAI providers add — but it handles the common questions gracefully
rather than repeating one canned line.
"""

from __future__ import annotations

import re

from marketcompass.contexts.copilot.domain.models import GuidanceSnapshot

# Hella's voice is soft even on the keyless path — a gentle sign-off rather than
# a blunt legal line. Only trading answers carry it; a greeting shouldn't.
_DISCLAIMER = "A gentle reminder — this is an algorithmic signal, not investment advice."

_GREETINGS = {"hi", "hello", "hey", "hii", "hiya", "yo", "namaste", "hola"}
_THANKS = {"thanks", "thank", "thankyou", "thx", "ty", "appreciate", "appreciated"}


def answer(snapshot: GuidanceSnapshot, question: str) -> str:
    q = question.lower().strip()
    words = set(re.findall(r"[a-z']+", q))

    # -- conversational intents (no trading disclaimer) ----------------------
    if words & _THANKS:
        return _thanks()
    if _is_identity(q, words):
        return _identity(snapshot)
    if _is_help(q, words):
        return _help(snapshot)
    if (words & _GREETINGS) and not _is_trading(q):
        return _greeting(snapshot)

    # -- trading intents (grounded in the guidance) --------------------------
    if _mentions(q, ("why", "reason", "explain", "rationale", "analys", "analyz", "read the")):
        body = _why(snapshot)
    elif _mentions(q, ("stop", "sl", "loss", "risk")):
        body = _stop(snapshot)
    elif _mentions(q, ("target", "tp", "profit", "upside")):
        body = _target(snapshot)
    elif _mentions(q, ("entry", "enter", "buy at", "sell at", "get in")):
        body = _entry(snapshot)
    elif _mentions(q, ("level", "support", "resistance", "wall", "pain")):
        body = _levels(snapshot)
    elif _mentions(q, ("contract", "strike", "option", " ce", " pe")):
        body = _contract(snapshot)
    else:
        body = _overview(snapshot)

    parts = [body]
    if not snapshot.is_actionable:
        parts.append("Do bear in mind this is built on simulated data — illustrative only.")
    parts.append(_DISCLAIMER)
    return " ".join(parts)


# -- intent detection --------------------------------------------------------


def _mentions(q: str, needles: tuple[str, ...]) -> bool:
    return any(needle in q for needle in needles)


def _is_identity(q: str, words: set[str]) -> bool:
    if "name" in words:
        return True
    return _mentions(q, ("who are you", "who r u", "what are you", "introduce", "about you"))


def _is_help(q: str, words: set[str]) -> bool:
    if "help" in words:
        return True
    return _mentions(q, ("what can you", "what do you do", "how can you", "what you can"))


def _is_trading(q: str) -> bool:
    return _mentions(q, ("call", "buy", "sell", "stop", "target", "level", "market", "nifty", "trade"))


# -- conversational answers --------------------------------------------------


def _identity(s: GuidanceSnapshot) -> str:
    return (
        "I'm Hella — your soft-spoken guide here in MarketCompass. I read the day's tape across "
        "OI, price action, levels and risk, and I'm always happy to walk you through "
        f"{s.symbol}'s setup, gently and clearly. What would you like to know?"
    )


def _greeting(s: GuidanceSnapshot) -> str:
    return (
        f"Hello, lovely to see you. I'm Hella. Ask me anything about {s.symbol}'s setup — the "
        "call and why, your stop, the target, or which levels matter — and I'll talk you through it."
    )


def _help(s: GuidanceSnapshot) -> str:
    return (
        f"I can read {s.symbol}'s current setup for you: the BUY/SELL/HOLD call and the reasoning, "
        "where a sensible stop and target sit, which levels matter, and how the four skills — OI "
        "Analysis, Price Action, Level-Based Trading and Risk Management — line up. Just ask gently."
    )


def _thanks() -> str:
    return "You're most welcome — I'm always here whenever you'd like to talk through the tape."


# -- trading answers (grounded) ----------------------------------------------


def _why(s: GuidanceSnapshot) -> str:
    voting = [skill for skill in s.skills if skill.score is not None]
    voting.sort(key=lambda skill: abs(skill.score or 0.0), reverse=True)
    reasons = " ".join(skill.headline for skill in voting[:2])
    return f"{s.symbol} reads {s.decision} at {s.confidence}% confidence. {reasons}".strip()


def _stop(s: GuidanceSnapshot) -> str:
    if s.stop is None:
        return f"There isn't a stop to point to just yet — the call is {s.decision}."
    return f"I'd keep the illustrative stop around {s.stop:,.0f}, at the nearest opposing level."


def _target(s: GuidanceSnapshot) -> str:
    if s.target is None:
        return f"There's no target to lean on right now — the call is {s.decision}."
    return f"The illustrative target sits near {s.target:,.0f}, the next level in the trade's direction."


def _entry(s: GuidanceSnapshot) -> str:
    if s.entry is None:
        return f"There's no active entry to consider — the call is {s.decision}, so patience is fine."
    return f"The reference entry is around {s.entry:,.0f}, near current spot/ATM."


def _levels(s: GuidanceSnapshot) -> str:
    support = "unknown" if s.support is None else f"{s.support:,.0f}"
    resistance = "unknown" if s.resistance is None else f"{s.resistance:,.0f}"
    return f"Support sits near {support} and resistance near {resistance}."


def _contract(s: GuidanceSnapshot) -> str:
    if not s.suggested_contract:
        return "There's no specific contract to suggest while the call is a HOLD."
    return f"An illustrative contract to consider: {s.suggested_contract}."


def _overview(s: GuidanceSnapshot) -> str:
    return f"Here's how I read {s.symbol}: {s.decision} at {s.confidence}% confidence. {s.rationale}"
