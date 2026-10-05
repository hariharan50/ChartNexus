"""Trading-session rules shared by every Options Lab series.

The Open Interest view and the Multi OI & Volume series read the same archive
and must answer the same three questions identically, or the two pages disagree
about what "today" and "the open" mean while sitting next to each other in the
same menu:

* what counts as a capture that has actually happened (:func:`drop_future`);
* where 09:15 is, in UTC (:func:`session_open_utc`);
* what the book looked like at 09:15 when nobody recorded it
  (:func:`session_open_frame`);
* what to draw on a day the archive never got written (:func:`live_proxy_frames`).

Pure: no clock of its own, no I/O. Callers pass ``now`` so tests can freeze it.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta, timezone

from chartnexus.contexts.options_analytics.application.ports import ChainSnapshot
from chartnexus.contexts.options_analytics.domain.oi_math import ChainRow

# India observes no DST, so a fixed +05:30 offset is correct and avoids needing
# tzdata on the host.
IST = timezone(timedelta(hours=5, minutes=30))
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)

# How late the first stored snapshot may be before the session open is
# reconstructed rather than taken from it.
#
# Zero, not a few minutes' grace: `oi_change` is the broker's change *since the
# 09:15 bell*, so a snapshot taken even one minute into the session already
# reports an OI that has moved off the open — anchoring the baseline to it makes
# "OI change" understate the real move by that first minute's drift. Kite and
# StockMojo both anchor at 09:15 (they show `oi - oi_change` there), and a
# five-minute grace was quietly disagreeing with them by up to a few lakh of OI
# on the headline number. So: use a stored frame only when it *is* the open
# (captured at or before 09:15); otherwise reconstruct 09:15 from `oi_change`,
# which is what the busy strikes need and what the other terminals do.
OPEN_TOLERANCE = timedelta(0)


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

    Volume is zeroed rather than carried over, for the same reason it is in
    :func:`live_proxy_frames`: it is cumulative from the bell, so the newest
    snapshot's figure is *today's whole traded volume*, not the volume as at
    09:15 — which was nothing. Copying it forward put the day's total at index 0
    of every contract's volume series, so the line opened at its own maximum and
    fell for the rest of the morning. Open interest is the opposite case: it
    carries over from the previous session, which is exactly why it is restated
    from ``oi_change`` instead of zeroed.

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
            replace(row, oi=max(0, row.oi - row.oi_change), oi_change=0, volume=0)
            for row in newest.rows
        ),
        # Deliberately no spot/ATM/futures: nobody recorded where the index was
        # at 09:15, and inventing one would draw the price line through a level
        # that never traded. Callers fall back to their payload-level values.
    )


def live_proxy_frames(
    rows: tuple[ChainRow, ...],
    now: datetime,
    *,
    spot: float | None = None,
    future_price: float | None = None,
) -> list[ChainSnapshot]:
    """A two-frame session synthesised from one live chain.

    The archive is written by a separate ingest process, so a machine that has
    not run it — or has not run it *yet* today — has no history at all. The Open
    Interest page has always handled that by reconstructing the open from
    ``oi_change`` and drawing open-vs-now; this is the same tier for the series
    pages, which otherwise render a blank panel all session on exactly the days
    the OI page next door is showing numbers.

    Two frames, not one: a single point plots nothing, and open-vs-now is the
    honest floor — it is genuinely all a broker that only answers "now" can tell
    us about a day nobody recorded.

    Volume is zeroed on the opening frame because it is cumulative from the
    bell: at 09:15 nothing had traded yet, so 0 is the observation, not a gap.
    Open interest is not zeroed — it carries over from the previous session, and
    ``oi - oi_change`` is the broker's own statement of what it opened at.

    Returns ``[]`` before the bell, which callers serve as an empty payload:
    there is no session yet to draw two ends of.
    """
    if not rows:
        return []

    open_ts = session_open_utc(now)
    now_ts = attach_utc(now)
    if now_ts <= open_ts:
        return []

    opening = ChainSnapshot(
        captured_at=open_ts,
        rows=tuple(
            replace(row, oi=max(0, row.oi - row.oi_change), oi_change=0, volume=0) for row in rows
        ),
        # No spot/ATM/future for the same reason as `session_open_frame`.
    )
    current = ChainSnapshot(
        captured_at=now_ts,
        rows=rows,
        spot=spot,
        future_price=future_price if future_price is not None else spot,
    )
    return [opening, current]


def for_expiry(snapshots: list[ChainSnapshot], expiry: str | None) -> list[ChainSnapshot]:
    """Keep only the captures that priced ``expiry``.

    The archive holds whichever expiry the ingest worker follows - the nearest
    one. Ask a page for a far expiry and the live chain obliges, but the
    archived frames behind the intraday series are still the near contract, so
    without this filter the page draws one expiry's header over another's rows
    and never says a word about it.

    Filtering instead of substituting is the point: an expiry the archive does
    not hold comes back empty, and the caller's own snapshot-count check then
    drops it to the live-proxy tier, which is the honest answer - open versus
    now, off the chain that expiry actually has.

    ``expiry`` of ``None`` means "whatever the backend picks", so everything is
    kept. Frames with no recorded expiry are kept too: they predate the column,
    and dropping them would silently empty the archive for every older session.
    """
    if expiry is None:
        return snapshots
    return [snap for snap in snapshots if snap.expiry in (None, expiry)]
