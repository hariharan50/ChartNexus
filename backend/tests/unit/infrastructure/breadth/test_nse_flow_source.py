"""The live flow source, served its own fixtures over a stubbed transport.

Two sessions are published — 21 and 22 September 2026 — and everything else
404s, which is what a holiday, a weekend and "not published yet" all look like
from here. The 22nd's files are the real ones; the 21st's board is derived
from them so the two differ by a known amount and the Change column can be
checked against a number rather than against itself.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from chartnexus.contexts.market_breadth.application.ports import (
    InstitutionalFlowSource,
)
from chartnexus.contexts.market_breadth.domain.flows import Participant, Segment
from chartnexus.infrastructure.breadth.flow_source import (
    SimulatedInstitutionalFlowSource,
)
from chartnexus.infrastructure.breadth.nse.flow_source import (
    NseInstitutionalFlowSource,
)
from chartnexus.infrastructure.time.clock import FixedClock
from chartnexus.shared_kernel.types.identifiers import TenantId

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "nse"
TENANT = TenantId("tenant-1")

SESSION = date(2026, 9, 22)
PREVIOUS = date(2026, 9, 21)

#: Midday UTC is late afternoon IST, so the exchange date and the server date
#: agree and the fixture does not drift across the 05:30 rollover.
TODAY = datetime(2026, 9, 23, 12, tzinfo=UTC)


# -- the stub exchange ---------------------------------------------------------


class FakeArchive:
    """Serves the fixtures for two sessions and 404s everything else."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        self._oi = (FIXTURES / "fao_participant_oi_22092026.csv").read_bytes()
        self._stats = (FIXTURES / "fii_stats_22-Sep-2026.xls").read_bytes()
        self._cash = (FIXTURES / "fiidii_trade_react.json").read_bytes()
        self._activity = (FIXTURES / "MA220926.csv").read_bytes()

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        if url.endswith("/api/fiidiiTradeReact"):
            return httpx.Response(200, content=self._cash)
        if "fao_participant_oi_22092026" in url:
            return httpx.Response(200, content=self._oi)
        if "fao_participant_oi_21092026" in url:
            return httpx.Response(200, content=_reshaped(self._oi, PREVIOUS))
        if "fii_stats_22-Sep-2026" in url:
            return httpx.Response(200, content=self._stats)
        if "MA220926" in url:
            return httpx.Response(200, content=self._activity)
        # Everything else: the archive's own 404 page, under a 200 — which is
        # what it really does, and the reason the parsers check the body.
        return httpx.Response(200, content=b"<!DOCTYPE html><html>Not found</html>")


#: How much every long leg is reduced by in the stand-in file for the 21st.
#: Only the longs move, so each participant's net moves by exactly this and
#: the Change column is checked against a value rather than against a zero.
_SHIFT = 1_000


def _reshaped(payload: bytes, session: date) -> bytes:
    """The 22nd's file, restamped and shifted, standing in for the 21st."""
    lines = payload.decode().splitlines()
    headers = lines[1].split(",")
    longs = {at for at, name in enumerate(headers) if name.strip().lower().endswith("long")}

    out = [lines[0].replace("Sep 22, 2026", f"Sep {session.day}, 2026"), lines[1]]
    for line in lines[2:]:
        out.append(
            ",".join(
                str(max(int(cell) - _SHIFT, 0)) if at in longs and cell.strip() else cell
                for at, cell in enumerate(line.split(","))
            )
        )
    return "\n".join(out).encode()


def build(archive: FakeArchive) -> tuple[NseInstitutionalFlowSource, httpx.AsyncClient]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(archive.handle))
    clock = FixedClock(TODAY)
    source = NseInstitutionalFlowSource(
        http,
        FakeRedis(),
        fallback=SimulatedInstitutionalFlowSource(clock),
        clock=clock,
    )
    return source, http


class FakeRedisCommands:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    async def hset(self, key: str, field: str, value: str) -> None:
        self.hashes.setdefault(key, {})[field] = value

    async def expire(self, key: str, ttl: int) -> None:
        return None


class FakeRedis:
    def __init__(self) -> None:
        self.client: Any = FakeRedisCommands()

    def key(self, *parts: str) -> str:
        return ":".join(parts)


# -- the port ------------------------------------------------------------------


def test_the_live_source_implements_the_port() -> None:
    archive = FakeArchive()
    source, _ = build(archive)
    assert isinstance(source, InstitutionalFlowSource)


# -- the calendar --------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_latest_session_is_the_last_one_with_a_published_file() -> None:
    """Today has no participant file yet, so the page shows yesterday's."""
    archive = FakeArchive()
    source, http = build(archive)
    async with http:
        days = await source.read(TENANT, sessions=60)
    assert days[-1].session_date == SESSION


@pytest.mark.asyncio
async def test_the_stepper_walks_to_published_sessions_only() -> None:
    archive = FakeArchive()
    source, http = build(archive)
    async with http:
        previous, following = await source.neighbours(TENANT, SESSION)
    assert previous == PREVIOUS
    # 22 September is the latest published day, so there is nowhere forward to
    # step — the arrow is disabled rather than walking into an empty board.
    assert following is None


# -- the session ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_session_carries_cash_and_the_four_derivative_segments() -> None:
    archive = FakeArchive()
    source, http = build(archive)
    async with http:
        days = await source.read(TENANT, sessions=60)

    latest = days[-1]
    cash = latest.segment(Segment.CASH)
    assert cash is not None
    assert cash.fii.net == Decimal("-3809.99")
    assert cash.dii is not None and cash.dii.net == Decimal("4120.07")

    index_options = latest.segment(Segment.INDEX_OPTIONS)
    assert index_options is not None
    assert index_options.fii.net == Decimal("-23213.82")
    # No DII line in any derivative segment: the exchange does not publish
    # one, and a zero there would read as "they did nothing".
    assert index_options.dii is None


@pytest.mark.asyncio
async def test_only_the_session_on_screen_costs_a_workbook() -> None:
    """Sixty sessions of rail figures would be sixty downloads for four numbers."""
    archive = FakeArchive()
    source, http = build(archive)
    async with http:
        await source.read(TENANT, sessions=60)
    assert sum("fii_stats" in url for url in archive.requests) == 1


@pytest.mark.asyncio
async def test_the_board_compares_against_the_previous_published_session() -> None:
    archive = FakeArchive()
    source, http = build(archive)
    async with http:
        rows = await source.read_open_interest(TENANT, SESSION)

    fii_futures = next(
        row
        for row in rows
        if row.participant is Participant.FII and row.segment is Segment.INDEX_FUTURES
    )
    assert fii_futures.net == -302_908
    # The stand-in file for the 21st holds a thousand fewer long contracts in
    # every leg, so the previous net sits a thousand lower and the change is
    # read against a real neighbour rather than against the same board.
    assert fii_futures.previous_net == -302_908 - _SHIFT
    assert fii_futures.change == _SHIFT


@pytest.mark.asyncio
async def test_the_index_level_is_the_sessions_own_close() -> None:
    archive = FakeArchive()
    source, http = build(archive)
    async with http:
        snapshot = await source.read_index(TENANT, SESSION, "NIFTY50")

    assert snapshot is not None
    assert snapshot.level == Decimal("23329.00")
    assert snapshot.previous_close == Decimal("23414.30")
    assert snapshot.as_of == SESSION.isoformat()


@pytest.mark.asyncio
async def test_an_unpublished_session_has_no_board_rather_than_an_empty_one() -> None:
    archive = FakeArchive()
    source, http = build(archive)
    async with http:
        rows = await source.read_open_interest(TENANT, date(2026, 9, 18))
    assert rows == []


# -- caching ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_published_file_is_fetched_once() -> None:
    archive = FakeArchive()
    source, http = build(archive)
    async with http:
        await source.read_open_interest(TENANT, SESSION)
        before = len(archive.requests)
        await source.read_open_interest(TENANT, SESSION)
    assert len(archive.requests) == before


@pytest.mark.asyncio
async def test_the_cash_journal_keeps_what_was_seen() -> None:
    """The only reading of that day's cash figure there will ever be.

    The exchange serves cash-market value for the latest session only, so a
    session that is not journalled while it is current cannot be recovered
    afterwards from anywhere.
    """
    archive = FakeArchive()
    source, http = build(archive)
    async with http:
        await source.read(TENANT, sessions=60)
        journalled = await source._store.hgetall("cash-journal")

    assert SESSION.isoformat() in journalled
    assert json.loads(journalled[SESSION.isoformat()])["fb"] == "9845.81"


# -- degrading --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unreachable_archive_falls_back_and_says_so() -> None:
    """The badge has to keep telling the truth about which source answered."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    clock = FixedClock(TODAY)
    http = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    source = NseInstitutionalFlowSource(
        http, FakeRedis(), fallback=SimulatedInstitutionalFlowSource(clock), clock=clock
    )
    async with http:
        assert source.source == "live"
        days = await source.read(TENANT, sessions=5)

    assert len(days) == 5
    assert source.source == "mock"


@pytest.mark.asyncio
async def test_the_generator_publishes_no_index_level() -> None:
    """A made-up close is the one figure a reader could check, and it would fail."""
    generator = SimulatedInstitutionalFlowSource(FixedClock(TODAY))
    assert await generator.read_index(TENANT, SESSION, "NIFTY50") is None
