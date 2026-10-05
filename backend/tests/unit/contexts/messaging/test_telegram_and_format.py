"""Telegram message chunking and the briefing → plain-text formatter."""

from __future__ import annotations

from datetime import date

from chartnexus.contexts.mme100.domain.briefing import Briefing
from chartnexus.entrypoints.mme100_runtime import format_briefing_text
from chartnexus.infrastructure.notifications.telegram.sender import _chunk


def test_short_text_is_one_chunk() -> None:
    assert _chunk("hello") == ["hello"]


def test_empty_text_is_no_chunks() -> None:
    assert _chunk("   ") == []


def test_long_text_splits_under_the_limit() -> None:
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(300))
    chunks = _chunk(text, limit=1000)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)


def test_over_long_single_line_is_hard_split() -> None:
    chunks = _chunk("y" * 2500, limit=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(chunks) == "y" * 2500


def test_format_briefing_strips_markdown_and_adds_header() -> None:
    briefing = Briefing(
        trading_day=date(2026, 8, 24),
        instruments=("NIFTY",),
        markdown="## NIFTY\n\n**Bias:** bullish\n\n---\n\n- watch 24500",
        source="live",
    )
    text = format_briefing_text(briefing)
    assert text.startswith("📊 MME100 Pre-Market Briefing — 2026-08-24")
    assert "**" not in text
    assert "## NIFTY" not in text
    assert "NIFTY" in text
    assert "watch 24500" in text


def test_format_briefing_flags_simulated_source() -> None:
    briefing = Briefing(
        trading_day=date(2026, 8, 24),
        instruments=("NIFTY",),
        markdown="stuff",
        source="mock",
    )
    assert "simulated" in format_briefing_text(briefing).lower()
