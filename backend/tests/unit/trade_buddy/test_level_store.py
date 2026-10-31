"""The JSON store: does a restart genuinely resume where the session left off?

The resume path is load-bearing. Without it a restart at 14:00 rebuilds every
level in IDLE and re-reports everything price already passed today, which trains
the reader to ignore the channel — the slow version of the alert spam failure.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

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
