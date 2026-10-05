"""The [STRYX CALL] parser reads a call back into structured fields.

Pins the round-trip the journal depends on: a full LIVE call, the NO TRADE /
WATCHING shortfalls, and the two invariants that keep a malformed answer from
ever being journaled as live — a LIVE with no stop is downgraded, and an
unparseable status defaults to NO TRADE.
"""

from __future__ import annotations

from chartnexus.contexts.stryx.domain import call_template as ct
from chartnexus.contexts.stryx.domain.call_template import Status

_LIVE = """[STRYX CALL]
Instrument: NIFTY 23100 CE
Entry Style: Breakout
Trigger: Close above 23,000 wall + volume + OI unwind
Entry: 23,050-23,080
SL: 22,950
Target 1: 23,200
Target 2: 23,500
Confidence: High
Reasoning: PCR 0.78->0.85 in 3 candles, CE wall OI dropped 18%.
Status: LIVE"""


def test_parses_a_full_live_call() -> None:
    call = ct.parse(_LIVE)
    assert call.status is Status.LIVE
    assert call.instrument == "NIFTY 23100 CE"
    assert call.entry_style == "Breakout"
    assert call.entry == "23,050-23,080"
    assert call.stop == "22,950"
    assert call.target1 == "23,200"
    assert call.target2 == "23,500"
    assert call.confidence == "High"
    assert call.reasoning is not None


def test_entry_line_not_confused_with_entry_style() -> None:
    # 'Entry:' must not swallow the 'Entry Style:' value and vice versa.
    call = ct.parse(_LIVE)
    assert call.entry == "23,050-23,080"
    assert call.entry_style == "Breakout"


def test_no_trade() -> None:
    call = ct.parse("[STRYX CALL]\nStatus: NO TRADE\nReasoning: No edge yet.")
    assert call.status is Status.NO_TRADE


def test_watching() -> None:
    assert ct.parse("Instrument: -\nStatus: WATCHING").status is Status.WATCHING


def test_live_without_stop_is_downgraded() -> None:
    # The "no stop = no call" invariant, enforced regardless of what the model wrote.
    call = ct.parse("Entry: 100\nStatus: LIVE")
    assert call.status is Status.NO_TRADE


def test_dash_placeholders_become_none() -> None:
    call = ct.parse("Instrument: -\nEntry: n/a\nStatus: NO TRADE")
    assert call.instrument is None
    assert call.entry is None


def test_unparseable_status_defaults_to_no_trade() -> None:
    assert ct.parse("some rambling with no template").status is Status.NO_TRADE


def test_is_call_true_for_a_call() -> None:
    assert ct.is_call(_LIVE) is True
    assert ct.is_call("[STRYX CALL]\nStatus: NO TRADE") is True


def test_is_call_false_for_conversation() -> None:
    # A friendly reply carries neither the header nor a Status line, so it must
    # not be journaled as a call.
    assert ct.is_call("Hey! I'm STRYX — the aggressive half of the desk. Want me to scan?") is False
    assert ct.is_call("") is False
