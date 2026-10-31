"""The HTTP surface: does the page actually receive what the engine computed?

This file exists because of a bug found at this layer. ``_settings`` passed
``marked_on`` and ``levels_stale`` to a response model that declares neither,
and Pydantic's default ``extra="ignore"`` dropped them without a word. Nothing
in the suite noticed, because every other test asserted on the objects rather
than on the bytes.

So these tests assert on the JSON a client receives. A field that does not
survive serialisation does not exist, and the only place that is observable is
here.

Worth being precise about what this does and does not catch. Removing a field
from a response model *is* caught — the ``/state`` tests fail outright, which
is the common direction of the mistake. Passing an argument a model ignores is
*not* caught by assertion alone, since the output is unchanged; what guards
that is ``TestTheSettingsPanelContract`` pinning the exact key set, so the
response and the panel's expectations cannot drift apart silently in either
direction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from chartnexus.contexts.trade_buddy.api.dependencies import build_services
from chartnexus.contexts.trade_buddy.api.router import router
from chartnexus.contexts.trade_buddy.application.use_cases import (
    ClearLevels,
    GetLevels,
    GetOverrides,
    SetLevels,
    SetOverrides,
)
from chartnexus.contexts.trade_buddy.domain.budget import WhatsAppBudget
from chartnexus.contexts.trade_buddy.domain.level import LevelMark, LevelRole
from chartnexus.infrastructure.trade_buddy.build_trade_buddy import TradeBuddyServices
from chartnexus.infrastructure.trade_buddy.clock import FakeClock
from chartnexus.infrastructure.transport.http.dependencies import Principal, get_principal
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId
from tests.unit.trade_buddy.conftest import (
    SESSION_START,
    FixedAtr,
    MemoryLevelStore,
    policy,
    window,
)

pytestmark = pytest.mark.unit

SESSION = SESSION_START.date()
YESTERDAY = SESSION - timedelta(days=1)

MARKS = (
    LevelMark(label="R1", price=24_700.0, role=LevelRole.RESISTANCE),
    LevelMark(label="S1", price=24_600.0, role=LevelRole.SUPPORT),
)


@dataclass
class _Claims:
    """Just enough of ``AccessTokenClaims`` for ``Principal``'s two properties."""

    subject: UserId
    tenant_id: TenantId


def _services(store: MemoryLevelStore) -> TradeBuddyServices:
    """The real use cases over in-memory ports.

    Nothing about the HTTP layer is worth testing against a mocked application:
    the question here is whether real values survive the trip out.
    """
    clock = FakeClock(SESSION_START)
    win = window()
    return TradeBuddyServices(
        get_levels=GetLevels(store=store),
        set_levels=SetLevels(store=store, window=win, clock=clock),
        clear_levels=ClearLevels(store=store),
        fire_test=None,  # type: ignore[arg-type]
        get_overrides=GetOverrides(store=store),
        set_overrides=SetOverrides(store=store),
        get_channels=None,  # type: ignore[arg-type]
        connect_channel=None,  # type: ignore[arg-type]
        link_chat=None,  # type: ignore[arg-type]
        test_channel=None,  # type: ignore[arg-type]
        set_channel_enabled=None,  # type: ignore[arg-type]
        disconnect_channel=None,  # type: ignore[arg-type]
        _store=store,
        _window=win,
        _clock=clock,
        _policy=policy(),
        _atr_source=FixedAtr(None),
        _cooldown=timedelta(minutes=20),
        _daily_cap=3,
        _whatsapp=WhatsAppBudget(limit=25, window=timedelta(hours=4)),
    )


@pytest.fixture
def marks_store() -> MemoryLevelStore:
    return MemoryLevelStore()


@pytest.fixture
def client(marks_store: MemoryLevelStore) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[build_services] = lambda: _services(marks_store)
    app.dependency_overrides[get_principal] = lambda: Principal(
        claims=_Claims(  # type: ignore[arg-type]
            subject=UserId(uuid.uuid4()), tenant_id=TenantId(uuid.uuid4())
        )
    )
    return TestClient(app)


class TestTheStaleFlagReachesTheClient:
    """The page's only way to explain a quiet morning."""

    def test_state_reports_yesterdays_levels_as_stale(self, client, marks_store):
        marks_store.mark("NIFTY", *MARKS, on=YESTERDAY)

        body = client.get("/api/v1/trade-buddy/state", params={"symbol": "NIFTY"}).json()

        assert body["levels_stale"] is True
        assert body["marked_on"] == YESTERDAY.isoformat()

    def test_state_reports_todays_levels_as_current(self, client, marks_store):
        marks_store.mark("NIFTY", *MARKS, on=SESSION)

        body = client.get("/api/v1/trade-buddy/state", params={"symbol": "NIFTY"}).json()

        assert body["levels_stale"] is False
        assert body["marked_on"] == SESSION.isoformat()

    def test_an_unmarked_instrument_is_not_stale(self, client):
        """Different problem, different message: there is nothing to be stale."""
        body = client.get("/api/v1/trade-buddy/state", params={"symbol": "NIFTY"}).json()

        assert body["levels_stale"] is False
        assert body["marked_on"] is None
        assert body["levels"] == []

    def test_the_watchlist_flags_only_the_stale_index(self, client, marks_store):
        marks_store.mark("NIFTY", *MARKS, on=YESTERDAY)
        marks_store.mark("BANKNIFTY", *MARKS, on=SESSION)

        rows = client.get("/api/v1/trade-buddy/watchlist").json()["instruments"]
        stale = {row["symbol"]: row["levels_stale"] for row in rows}

        assert stale["NIFTY"] is True
        assert stale["BANKNIFTY"] is False
        assert stale["SENSEX"] is False

    def test_levels_carries_the_stamp(self, client, marks_store):
        marks_store.mark("NIFTY", *MARKS, on=YESTERDAY)

        body = client.get("/api/v1/trade-buddy/levels", params={"symbol": "NIFTY"}).json()

        assert body["marked_on"] == YESTERDAY.isoformat()
        # The levels themselves still come back: the page must be able to show
        # what is about to be replaced, not merely that something is.
        assert len(body["levels"]) == 2


class TestMarkingStampsTheSession:
    def test_a_put_stamps_today_and_clears_the_stale_flag(self, client, marks_store):
        marks_store.mark("NIFTY", *MARKS, on=YESTERDAY)

        put = client.put(
            "/api/v1/trade-buddy/levels",
            json={
                "symbol": "NIFTY",
                "levels": [
                    {"label": "R1", "price": 24_700.0, "role": "resistance"},
                    {"label": "S1", "price": 24_600.0, "role": "support"},
                ],
            },
        )
        assert put.status_code == 200

        body = client.get("/api/v1/trade-buddy/state", params={"symbol": "NIFTY"}).json()
        assert body["levels_stale"] is False
        assert body["marked_on"] == SESSION.isoformat()

    def test_re_marking_is_what_a_morning_looks_like(self, client, marks_store):
        """Yesterday's levels in, today's out, one request between them."""
        marks_store.mark("NIFTY", *MARKS, on=YESTERDAY)
        before = client.get("/api/v1/trade-buddy/levels", params={"symbol": "NIFTY"}).json()
        assert before["marked_on"] == YESTERDAY.isoformat()

        client.put(
            "/api/v1/trade-buddy/levels",
            json={
                "symbol": "NIFTY",
                "levels": [{"label": "R1", "price": 24_800.0, "role": "resistance"}],
            },
        )

        after = client.get("/api/v1/trade-buddy/levels", params={"symbol": "NIFTY"}).json()
        assert after["marked_on"] == SESSION.isoformat()
        assert [level["price"] for level in after["levels"]] == [24_800.0]


class TestTheSettingsPanelContract:
    """What the panel renders, as JSON.

    The regression this file opens with: two fields were passed to this
    response and silently dropped. Asserting the exact key set is what makes
    that visible — a field nobody asserts on is a field nobody notices losing.
    """

    def test_it_returns_exactly_the_keys_the_panel_reads(self, client, marks_store):
        marks_store.mark("NIFTY", *MARKS, on=SESSION)

        body = client.get("/api/v1/trade-buddy/settings", params={"symbol": "NIFTY"}).json()

        assert set(body) == {
            "symbol",
            "bands",
            "cooldown_minutes",
            "daily_alert_cap",
            "defaults",
            "overrides",
        }

    def test_staleness_is_not_duplicated_here(self, client, marks_store):
        """It belongs to ``/state``, which the page renders above this panel.
        Two sources for one fact is two things to keep in step."""
        marks_store.mark("NIFTY", *MARKS, on=YESTERDAY)

        body = client.get("/api/v1/trade-buddy/settings", params={"symbol": "NIFTY"}).json()

        assert "levels_stale" not in body
        assert "marked_on" not in body


class TestSymbolValidation:
    def test_an_unwatched_index_is_refused_with_the_list(self, client):
        response = client.get("/api/v1/trade-buddy/state", params={"symbol": "MIDCPNIFTY"})

        assert response.status_code == 422
        assert "NIFTY, BANKNIFTY, SENSEX" in response.json()["detail"]
