"""The [STRYX CALL] output contract, plus the parser that reads it back.

STRYX answers in a fixed, scannable template so a human can act in seconds and so
every call — LIVE, NO TRADE or WATCHING — can be journaled and later backtested
for hit-rate. :data:`CONTRACT` is the exact shape STRYX is told to emit;
:func:`parse` reads that shape back into a :class:`StryxCall` for the journal,
degrading gracefully when a field is absent (a NO TRADE has no entry/stop).

Pure and deterministic — no model needed to test the round-trip.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    LIVE = "LIVE"
    NO_TRADE = "NO_TRADE"
    WATCHING = "WATCHING"


@dataclass(frozen=True, slots=True)
class StryxCall:
    """A parsed STRYX call, ready for the journal."""

    status: Status
    instrument: str | None = None
    entry_style: str | None = None
    entry: str | None = None
    stop: str | None = None
    target1: str | None = None
    target2: str | None = None
    confidence: str | None = None
    reasoning: str | None = None


# The exact template STRYX must emit. Kept terse — it is both the instruction and
# the thing :func:`parse` reads back.
CONTRACT = (
    "Answer in EXACTLY this template and nothing outside it:\n"
    "[STRYX CALL]\n"
    "Instrument: <e.g. NIFTY 23100 CE, or '-' if no trade>\n"
    "Entry Style: <one of Early / Breakout / Momentum / Liquidity / No-Retracement, or '-'>\n"
    "Trigger: <the condition that fired it, or why none did>\n"
    "Entry: <price or zone, or '-'>\n"
    "SL: <stop price — MANDATORY for a LIVE call, or '-'>\n"
    "Target 1: <price, or '-'>\n"
    "Target 2: <price, or '-'>\n"
    "Confidence: <High / Medium / Speculative, or '-'>\n"
    "Reasoning: <1-2 lines max, grounded in the numbers you read>\n"
    "Status: <LIVE / NO TRADE / WATCHING>\n\n"
    "Rules for the template: a LIVE status REQUIRES both Entry and SL. If you have no edge, "
    "return Status: NO TRADE — say so as forcefully as you would a LIVE call. If a setup is "
    "building but not yet triggered, return Status: WATCHING."
)

_FIELD = {
    "instrument": r"Instrument",
    "entry_style": r"Entry Style",
    "entry": r"Entry",
    "stop": r"SL",
    "target1": r"Target\s*1",
    "target2": r"Target\s*2",
    "confidence": r"Confidence",
    "reasoning": r"Reasoning",
}


def _field(label: str, text: str) -> str | None:
    m = re.search(rf"^\s*{label}\s*:\s*(.+?)\s*$", text, re.IGNORECASE | re.MULTILINE)
    if m is None:
        return None
    value = m.group(1).strip()
    # A dash / n/a placeholder means "not applicable", not a real value.
    if value in {"-", "--", "—", ""} or value.lower() in {"n/a", "na", "none"}:
        return None
    return value


def _status(text: str) -> Status:
    m = re.search(r"^\s*Status\s*:\s*(.+?)\s*$", text, re.IGNORECASE | re.MULTILINE)
    raw = (m.group(1) if m else "").strip().upper()
    if "NO" in raw and "TRADE" in raw:
        return Status.NO_TRADE
    if raw.startswith("WATCH"):
        return Status.WATCHING
    if raw.startswith("LIVE"):
        return Status.LIVE
    # No parseable status line: treat as NO TRADE so a malformed answer can never
    # be journaled (or acted on) as a live call.
    return Status.NO_TRADE


def is_call(answer: str) -> bool:
    """True when an answer is an actual [STRYX CALL], not plain conversation.

    Gates journaling: a friendly "hi, I'm STRYX" reply carries neither the header
    nor a ``Status:`` line, so it is never logged as a (NO TRADE) call.
    """
    text = answer or ""
    if "[STRYX CALL]" in text:
        return True
    return re.search(r"^\s*Status\s*:", text, re.IGNORECASE | re.MULTILINE) is not None


def parse(answer: str) -> StryxCall:
    """Read a STRYX answer back into a :class:`StryxCall` for journaling.

    A ``LIVE`` status is only honoured when both an entry and a stop are present;
    otherwise it is downgraded to ``NO_TRADE`` — the "no stop = no call" invariant
    enforced deterministically, independent of what the model wrote.
    """
    text = answer or ""
    status = _status(text)
    fields = {name: _field(label, text) for name, label in _FIELD.items()}

    if status is Status.LIVE and not (fields["entry"] and fields["stop"]):
        status = Status.NO_TRADE

    return StryxCall(status=status, **fields)
