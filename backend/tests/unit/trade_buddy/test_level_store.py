"""The JSON store: does a restart genuinely resume where the session left off?

The resume path is load-bearing. Without it a restart at 14:00 rebuilds every
level in IDLE and re-reports everything price already passed today, which trains
the reader to ignore the channel — the slow version of the alert spam failure.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from chartnexus.contexts.trade_buddy.application.ports import AlertRecord
from chartnexus.contexts.trade_buddy.domain.events import AlertKind
from chartnexus.contexts.trade_buddy.domain.level import LevelMark, LevelRole
from chartnexus.contexts.trade_buddy.domain.state import LevelState, LevelWatcher
from chartnexus.infrastructure.trade_buddy.json_level_store import JsonLevelStore
from tests.unit.trade_buddy.conftest import SESSION_START, at, bands

pytestmark = pytest.mark.unit

SYMBOL = "NSE:NIFTY50-INDEX"
#: The session the fixtures mark for.
SESSION = SESSION_START.date()

MARKS = (
    LevelMark(label="R1", price=24_700.0, role=LevelRole.RESISTANCE),
    LevelMark(label="S1", price=24_600.0, role=LevelRole.SUPPORT),
)


@pytest.fixture
def store(tmp_path) -> JsonLevelStore:
    return JsonLevelStore(directory=tmp_path, bands=bands())


class TestMarks:
    async def test_marks_round_trip(self, store):
        await store.save_marks(SYMBOL, MARKS, SESSION)
        assert (await store.load_marks(SYMBOL)).marks == MARKS

    async def test_an_unknown_symbol_loads_empty(self, store):
        assert (await store.load_marks("NSE:NOTHING-INDEX")).marks == ()

    async def test_saving_marks_replaces_rather_than_appends(self, store):
        await store.save_marks(SYMBOL, MARKS, SESSION)
        await store.save_marks(SYMBOL, (MARKS[0],), SESSION)
        assert (await store.load_marks(SYMBOL)).marks == (MARKS[0],)

    async def test_clear_removes_everything_for_the_symbol(self, store):
        await store.save_marks(SYMBOL, MARKS, SESSION)
        await store.clear(SYMBOL)
        assert (await store.load_marks(SYMBOL)).marks == ()
        assert await store.load_watchers(SYMBOL) == ()

    async def test_clear_is_idempotent(self, store):
        await store.clear(SYMBOL)  # never existed
        await store.clear(SYMBOL)

    async def test_a_colon_in_the_symbol_does_not_break_the_filename(self, store, tmp_path):
        """'NSE:NIFTY50-INDEX' contains a colon, which is illegal on Windows."""
        await store.save_marks(SYMBOL, MARKS, SESSION)
        written = list(tmp_path.glob("*.json"))
        assert len(written) == 1
        assert ":" not in written[0].name


class TestTheSessionStamp:
    """Marks are a daily artefact, and the file outlives the day.

    Without the stamp nothing on disk distinguishes this morning's levels from
    Friday's, and a watcher resuming on Monday would compare live price against
    four-day-old numbers with full confidence. The stamp is what lets it refuse.
    """

    async def test_the_session_is_persisted_and_read_back(self, store):
        await store.save_marks(SYMBOL, MARKS, SESSION)
        assert (await store.load_marks(SYMBOL)).marked_on == SESSION

    async def test_yesterdays_file_reads_back_as_stale(self, store):
        yesterday = SESSION - timedelta(days=1)
        await store.save_marks(SYMBOL, MARKS, yesterday)

        loaded = await store.load_marks(SYMBOL)
        assert loaded.is_stale(SESSION)
        assert not loaded.is_current(SESSION)

    async def test_re_marking_clears_the_staleness(self, store):
        await store.save_marks(SYMBOL, MARKS, SESSION - timedelta(days=1))
        await store.save_marks(SYMBOL, MARKS, SESSION)

        loaded = await store.load_marks(SYMBOL)
        assert loaded.is_current(SESSION)
        assert not loaded.is_stale(SESSION)

    async def test_the_stamp_is_a_plain_iso_date_on_disk(self, store, tmp_path):
        """Readable with `cat` when diagnosing a quiet morning."""
        await store.save_marks(SYMBOL, MARKS, SESSION)
        written = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
        assert written["marked_on"] == SESSION.isoformat()

    async def test_a_file_from_before_the_stamp_existed_is_discarded(self, store, tmp_path):
        """The version bump that introduced `marked_on`.

        A v3 file has marks and no stamp. Reading it as-is would leave the
        staleness question unanswerable, so the version check drops it — and an
        instrument with no marks prompts for levels rather than warning about
        old ones, which is the correct thing to say.
        """
        path = tmp_path / "NSE_NIFTY50-INDEX.json"
        path.write_text(
            json.dumps(
                {
                    "version": 3,
                    "marks": [{"label": "R1", "price": 24_700.0, "role": "resistance"}],
                }
            ),
            encoding="utf-8",
        )

        loaded = await store.load_marks(SYMBOL)
        assert loaded.marks == ()
        assert loaded.marked_on is None
        # Empty, so neither stale nor current: there is nothing to be stale.
        assert not loaded.is_stale(SESSION)


class TestWatcherResume:
    async def test_state_and_role_survive_a_round_trip(self, store):
        watcher = LevelWatcher(symbol=SYMBOL, mark=MARKS[0], bands=bands())
        watcher.state = LevelState.BROKEN
        watcher.role = LevelRole.SUPPORT  # flipped by the break
        watcher.break_sign = 1
        await store.save_marks(SYMBOL, MARKS, SESSION)
        await store.save_watchers(SYMBOL, (watcher,))

        (resumed,) = await store.load_watchers(SYMBOL)

        assert resumed.state is LevelState.BROKEN
        assert resumed.role is LevelRole.SUPPORT
        assert resumed.break_sign == 1
        assert resumed.mark == MARKS[0]

    async def test_a_pending_break_is_downgraded_on_resume(self, store):
        """The safety property.

        ``pending_since`` is a monotonic reading and means nothing after a
        restart. Resuming BREAK_PENDING as-is would let the next tick confirm
        against a stale origin — a break the market never actually held.
        """
        watcher = LevelWatcher(symbol=SYMBOL, mark=MARKS[0], bands=bands())
        watcher.state = LevelState.BREAK_PENDING
        watcher.pending_since = 1234.5
        watcher.break_sign = 1
        await store.save_watchers(SYMBOL, (watcher,))

        (resumed,) = await store.load_watchers(SYMBOL)

        assert resumed.state is LevelState.TOUCHED
        assert resumed.pending_since is None
        assert resumed.break_sign is None

    async def test_a_resumed_pending_break_must_re_earn_its_hold(self, store):
        """Following on: the downgraded watcher cannot confirm instantly."""
        watcher = LevelWatcher(symbol=SYMBOL, mark=MARKS[0], bands=bands())
        watcher.state = LevelState.BREAK_PENDING
        watcher.pending_since = 0.0
        watcher.break_sign = 1
        await store.save_watchers(SYMBOL, (watcher,))
        (resumed,) = await store.load_watchers(SYMBOL)

        # Past the buffer again, but only one second in.
        assert resumed.observe(24_715.0, 1_000.0, at(1.0)) == []
        assert resumed.state is LevelState.BREAK_PENDING
        # Still nothing until the full hold elapses.
        assert resumed.observe(24_716.0, 1_019.0, at(19.0)) == []
        events = resumed.observe(24_717.0, 1_020.0, at(20.0))
        assert len(events) == 1

    async def test_marks_and_watchers_coexist_in_one_file(self, store):
        watcher = LevelWatcher(symbol=SYMBOL, mark=MARKS[0], bands=bands())
        await store.save_marks(SYMBOL, MARKS, SESSION)
        await store.save_watchers(SYMBOL, (watcher,))

        assert (await store.load_marks(SYMBOL)).marks == MARKS
        assert len(await store.load_watchers(SYMBOL)) == 1


class TestCorruption:
    async def test_unreadable_json_degrades_to_empty_rather_than_raising(self, store, tmp_path):
        """A crash loop is worse than losing today's resume state."""
        path = next(iter([tmp_path / "NSE_NIFTY50-INDEX.json"]))
        path.write_text("{not json at all", encoding="utf-8")

        assert (await store.load_marks(SYMBOL)).marks == ()
        assert await store.load_watchers(SYMBOL) == ()

    async def test_a_future_version_is_ignored(self, store, tmp_path):
        path = tmp_path / "NSE_NIFTY50-INDEX.json"
        path.write_text(json.dumps({"version": 999, "marks": []}), encoding="utf-8")

        assert (await store.load_marks(SYMBOL)).marks == ()

    async def test_a_write_leaves_no_temp_file_behind(self, store, tmp_path):
        await store.save_marks(SYMBOL, MARKS, SESSION)
        assert list(tmp_path.glob("*.tmp")) == []


class TestAlertHistory:
    """The day's log. Written by the worker, read by the API, kept for a session."""

    def _record(self, **over):
        fields = {
            "kind": AlertKind.TOUCHED,
            "label": "R1",
            "level_price": 24_700.0,
            "price": 24_703.0,
            "role_before": LevelRole.RESISTANCE,
            "role_after": LevelRole.RESISTANCE,
            "at": SESSION_START,
            "session": SESSION,
            "channels": ("telegram",),
        }
        fields.update(over)
        return AlertRecord(**fields)

    async def test_a_record_round_trips_whole(self, store):
        record = self._record()
        await store.append_alert(SYMBOL, record)

        assert await store.load_alerts(SYMBOL, SESSION) == (record,)

    async def test_an_unknown_symbol_has_no_history(self, store):
        assert await store.load_alerts(SYMBOL, SESSION) == ()

    async def test_the_channels_that_took_it_survive(self, store):
        """The one field that cannot be reconstructed from the event later."""
        await store.append_alert(SYMBOL, self._record(channels=("telegram", "whatsapp")))

        (back,) = await store.load_alerts(SYMBOL, SESSION)
        assert back.channels == ("telegram", "whatsapp")

    async def test_nothing_delivered_is_recorded_as_such(self, store):
        """An empty tuple is a fact, not a missing value: the engine fired and
        no channel took it, which is a different fault from never firing."""
        await store.append_alert(SYMBOL, self._record(channels=()))

        (back,) = await store.load_alerts(SYMBOL, SESSION)
        assert back.channels == ()

    async def test_newest_first(self, store):
        await store.append_alert(SYMBOL, self._record(label="R1", at=at(0)))
        await store.append_alert(SYMBOL, self._record(label="S1", at=at(60)))

        assert [r.label for r in await store.load_alerts(SYMBOL, SESSION)] == ["S1", "R1"]

    async def test_a_new_session_retires_the_old_log(self, store):
        """Pruned by the arriving record, not by a timer.

        The first alert of the morning is what drops yesterday's, so there is
        no window in which a stale log is still being served.
        """
        yesterday = SESSION - timedelta(days=1)
        await store.append_alert(SYMBOL, self._record(label="R3", session=yesterday))
        await store.append_alert(SYMBOL, self._record(label="R1", session=SESSION))

        assert await store.load_alerts(SYMBOL, yesterday) == ()
        assert [r.label for r in await store.load_alerts(SYMBOL, SESSION)] == ["R1"]

    async def test_the_log_is_capped_and_keeps_the_most_recent(self, store):
        for i in range(205):
            await store.append_alert(SYMBOL, self._record(label=f"L{i}", at=at(i)))

        history = await store.load_alerts(SYMBOL, SESSION)
        assert len(history) == 200
        # Newest first, so the head is the last one written and the oldest
        # five have been dropped rather than the newest five refused.
        assert history[0].label == "L204"
        assert history[-1].label == "L5"

    async def test_history_coexists_with_marks_and_watchers(self, store):
        await store.save_marks(SYMBOL, MARKS, SESSION)
        await store.append_alert(SYMBOL, self._record())
        watcher = LevelWatcher(symbol=SYMBOL, mark=MARKS[0], bands=bands())
        await store.save_watchers(SYMBOL, (watcher,))

        assert (await store.load_marks(SYMBOL)).marks == MARKS
        assert len(await store.load_watchers(SYMBOL)) == 1
        assert len(await store.load_alerts(SYMBOL, SESSION)) == 1

    async def test_clear_drops_the_history_too(self, store):
        await store.append_alert(SYMBOL, self._record())
        await store.clear(SYMBOL)

        assert await store.load_alerts(SYMBOL, SESSION) == ()

    async def test_a_v4_file_keeps_its_marks_and_reads_as_no_alerts(self, store, tmp_path):
        """The version bump must not wipe a live session.

        v4 is what every deployed instance has on disk when this ships. If the
        reader rejected it the way it rejects v3, a mid-morning deploy would
        drop today's marks and watcher states — re-reporting every level price
        had already passed, which is the exact failure the resume path exists
        to prevent. A missing `alerts` key simply means nothing has fired.
        """
        path = tmp_path / "NSE_NIFTY50-INDEX.json"
        path.write_text(
            json.dumps(
                {
                    "version": 4,
                    "marked_on": SESSION.isoformat(),
                    "marks": [{"label": "R1", "price": 24_700.0, "role": "resistance"}],
                }
            ),
            encoding="utf-8",
        )

        loaded = await store.load_marks(SYMBOL)
        assert [m.label for m in loaded.marks] == ["R1"]
        assert loaded.marked_on == SESSION
        assert await store.load_alerts(SYMBOL, SESSION) == ()

    async def test_appending_to_a_v4_file_upgrades_it_in_place(self, store, tmp_path):
        path = tmp_path / "NSE_NIFTY50-INDEX.json"
        path.write_text(
            json.dumps({"version": 4, "marked_on": SESSION.isoformat(), "marks": []}),
            encoding="utf-8",
        )

        await store.append_alert(SYMBOL, self._record())

        written = json.loads(path.read_text(encoding="utf-8"))
        assert written["version"] == 5
        assert len(written["alerts"]) == 1

    async def test_an_unreadable_row_is_skipped_rather_than_failing_the_read(self, store, tmp_path):
        """One hand-edited entry must not hide a day of good ones."""
        await store.append_alert(SYMBOL, self._record(label="R1"))
        path = tmp_path / "NSE_NIFTY50-INDEX.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["alerts"].insert(0, {"kind": "nonsense", "session": SESSION.isoformat()})
        path.write_text(json.dumps(data), encoding="utf-8")

        assert [r.label for r in await store.load_alerts(SYMBOL, SESSION)] == ["R1"]
