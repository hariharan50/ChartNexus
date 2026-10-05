"""Build the text digest HUGIN's chat and caller reason over — pure, no I/O.

HUGIN is memory-grounded: its chat and its calls see only what HUGIN has itself
observed and learned, never the live market tools. This module renders that memory
(recent hourly reads, the graded track record, and the weighted lessons) into a
compact block the LLM is told to treat as its only source of truth.

A ``skills`` slot is reserved but unused for now — uploaded skills will be folded
in here in a later phase without changing callers.
"""

from __future__ import annotations

from chartnexus.contexts.hugin.domain.lesson import Lesson
from chartnexus.contexts.hugin.domain.observation import Observation


def build_digest(
    *,
    instrument: str,
    today: tuple[Observation, ...],
    lessons: tuple[Lesson, ...],
    hit_rate_today: float | None,
    overall_hit_rate: float | None,
    recent_calls: tuple[str, ...] = (),
    skills: str = "",
) -> str:
    """Render HUGIN's memory for ``instrument`` into a single grounding block."""
    parts: list[str] = [f"HUGIN MEMORY — {instrument}", ""]

    parts.append("Track record:")
    parts.append(f"- Today's hit-rate: {_pct(hit_rate_today)}")
    parts.append(f"- All-time hit-rate: {_pct(overall_hit_rate)}")
    parts.append("")

    parts.append("Today's hourly reads (oldest first):")
    if today:
        parts.extend(_render_observation(obs) for obs in today)
    else:
        parts.append("- (none yet today)")
    parts.append("")

    parts.append("Lessons learned (most reliable first):")
    if lessons:
        parts.extend(
            f"- [{lsn.dedup_key}] {lsn.text} "
            f"(reliability {round(lsn.reliability * 100)}%, {lsn.hits} hits / {lsn.misses} misses)"
            for lsn in lessons
        )
    else:
        parts.append("- (none yet)")

    if recent_calls:
        parts.append("")
        parts.append("Recent calls HUGIN has made:")
        parts.extend(f"- {line}" for line in recent_calls)

    if skills:
        parts.append("")
        parts.append("Attached skills:")
        parts.append(skills)

    return "\n".join(parts)


def is_empty(today: tuple[Observation, ...], lessons: tuple[Lesson, ...]) -> bool:
    """True when HUGIN has nothing to reason over yet (guides the 'not learned' reply)."""
    return not today and not lessons


def _render_observation(obs: Observation) -> str:
    grade = f", graded {obs.grade.value}" if obs.grade is not None else ""
    return (
        f"- {obs.tick_at.isoformat()} {obs.bias.value}: {obs.expectation}"
        f" (call {obs.call_wall}, put {obs.put_wall}, key {obs.key_level}){grade}"
    )


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{round(value * 100)}%"
