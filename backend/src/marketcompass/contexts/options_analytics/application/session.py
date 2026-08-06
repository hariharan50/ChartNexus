"""Trading-session rules shared by every Options Lab series.

The Open Interest view and the Multi OI & Volume series read the same archive
and must answer the same three questions identically, or the two pages disagree
about what "today" and "the open" mean while sitting next to each other in the
same menu:

* what counts as a capture that has actually happened (:func:`drop_future`);
* where 09:15 is, in UTC (:func:`session_open_utc`);
* what the book looked like at 09:15 when nobody recorded it
  (:func:`session_open_frame`).

Pure: no clock of its own, no I/O. Callers pass ``now`` so tests can freeze it.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta, timezone

from marketcompass.contexts.options_analytics.application.ports import ChainSnapshot

# India observes no DST, so a fixed +05:30 offset is correct and avoids needing
# tzdata on the host.
IST = timezone(timedelta(hours=5, minutes=30))
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)

# How late the first stored snapshot may be before the session open is
# reconstructed rather than taken from it. One capture interval's grace.
OPEN_TOLERANCE = timedelta(minutes=5)


def attach_utc(moment: datetime) -> datetime:
    """Naive DB datetimes are UTC; attach it. Aware datetimes pass through."""
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def iso(moment: datetime) -> str:
    """A UTC ISO timestamp, whatever the caller had."""
    return attach_utc(moment).astimezone(UTC).isoformat()


def future_of(snapshot: ChainSnapshot) -> float | None:
    """The price a chart overlay should plot for this capture.

    The tradable current-month future, falling back to spot only for rows
    captured before that column existed. On a chart of option positions the
    index level is the one price nobody in the picture can deal at.

    ``None`` on the reconstructed 09:15 frame is deliberate: nobody recorded
    where the market was at the bell, and the line should start where the
    recording does rather than reach back to a level never observed.
    """
    return snapshot.future_price if snapshot.future_price is not None else snapshot.spot


def session_open_utc(now: datetime) -> datetime:
    """The 09:15 IST bell on ``now``'s trading date, expressed in UTC."""
    now_ist = attach_utc(now).astimezone(IST)
    open_ist = now_ist.replace(
        hour=SESSION_OPEN.hour, minute=SESSION_OPEN.minute, second=0, microsecond=0
    )
    return open_ist.astimezone(UTC)


def drop_future(snapshots: list[ChainSnapshot], now: datetime) -> list[ChainSnapshot]:
    """Discard captures that have not happened yet.

    Real ingest cannot produce one, but a seeded or restored day can, and the
    effect is that a tool's "as of" reads 15:30 all morning while the newest
    frame reports a market that does not exist.
    """
    return [snap for snap in snapshots if attach_utc(snap.captured_at) <= now]


def session_open_frame(ordered: list[ChainSnapshot]) -> ChainSnapshot | None:
    """A 09:15 frame reconstructed from the broker's day-change field.

    The archive only holds what was captured, so a worker started at 13:01
    leaves no morning: the baseline sits at 13:01 and "OI change" silently means
    "change since lunchtime" — the most-read number on the page, quietly wrong.

    It does not need to have been captured. ``oi_change`` is the change *since
    the session open* as the broker reports it, so ``oi - oi_change`` is the
    09:15 book, and reading it off the newest snapshot gives the most current
    version of it.

    ``ordered`` must be sorted oldest-first. Returns ``None`` when the archive
    already reaches back to the open.
    """
    if not ordered:
        return None

    newest = ordered[-1]
    open_ts = session_open_utc(attach_utc(newest.captured_at))
    if attach_utc(ordered[0].captured_at) <= open_ts + OPEN_TOLERANCE:
        return None

    return ChainSnapshot(
        captured_at=open_ts,
        rows=tuple(
            replace(row, oi=max(0, row.oi - row.oi_change), oi_change=0) for row in newest.rows
        ),
        # Deliberately no spot/ATM/futures: nobody recorded where the index was
        # at 09:15, and inventing one would draw the price line through a level
        # that never traded. Callers fall back to their payload-level values.
    )
