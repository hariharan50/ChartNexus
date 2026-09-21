"""Getting a catalog into a process that started without one.

An empty registry is not a degraded mode — no instrument resolves at all, so
every request in the process fails. These cover the recovery, which was missing:
the API once started a few seconds ahead of Postgres, the startup load failed,
nothing retried, and the whole application answered "NIFTY is not a tradeable
instrument" until it was restarted by hand.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import cast

import pytest

from marketcompass.bootstrap.container import Container
from marketcompass.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)
from marketcompass.entrypoints import catalog_runtime
from marketcompass.infrastructure.catalog import registry

pytestmark = pytest.mark.unit

# Every collaborator these exercise is patched out, so the container is never
# touched — only passed through.
NO_CONTAINER = cast("Container", object())


def instrument(symbol: str = "NIFTY") -> Instrument:
    return Instrument(
        symbol=symbol,
        kind=InstrumentKind.INDEX,
        name=symbol,
        exchange="NSE",
        lot_size=65,
        tick_size=Decimal("0.10"),
        spot_symbol=f"NSE:{symbol}-INDEX",
        futures_root=f"NSE:{symbol}",
    )


@pytest.fixture(autouse=True)
def _no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retries are the thing under test; waiting between them is not."""
    monkeypatch.setattr(catalog_runtime, "_RETRY_BASE_SECONDS", 0.0)
    monkeypatch.setattr(catalog_runtime, "_RETRY_CEILING_SECONDS", 0.0)


@pytest.fixture(autouse=True)
def _empty_registry() -> Iterator[None]:
    with registry.installed(()):
        yield


async def test_a_populated_registry_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """The common case: a reload under --reload must not re-read anything."""
    reads = 0

    async def never(_: object) -> list[Instrument]:
        nonlocal reads
        reads += 1
        return []

    monkeypatch.setattr(catalog_runtime, "_read_catalog", never)

    with registry.installed([instrument()]):
        loaded = await catalog_runtime.ensure_registry(NO_CONTAINER, stop=asyncio.Event())

    assert loaded == 1
    assert reads == 0


async def test_a_database_that_is_not_up_yet_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression. The catalog was in the database the whole time — only
    this process failed to read it, because it asked too early."""
    attempts = 0

    async def flaky(_: object) -> list[Instrument]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionRefusedError("the database is still starting")
        return [instrument()]

    monkeypatch.setattr(catalog_runtime, "_read_catalog", flaky)

    loaded = await catalog_runtime.ensure_registry(NO_CONTAINER, stop=asyncio.Event())

    assert loaded == 1
    assert attempts == 2
    assert "NIFTY" in registry.current()


async def test_an_unreachable_database_does_not_trigger_a_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sync downloads ~19 MB of symbol masters and then writes to the very
    database that just refused the read. Retrying the read is the whole fix."""
    synced = 0

    async def down(_: object) -> list[Instrument]:
        raise ConnectionRefusedError("down")

    async def sync(_: object) -> None:
        nonlocal synced
        synced += 1

    monkeypatch.setattr(catalog_runtime, "_read_catalog", down)
    monkeypatch.setattr(catalog_runtime, "sync_once", sync)

    stop = asyncio.Event()

    async def give_up() -> None:
        await asyncio.sleep(0)
        stop.set()

    _, loaded = await asyncio.gather(
        give_up(), catalog_runtime.ensure_registry(NO_CONTAINER, stop=stop)
    )

    assert loaded == 0
    assert synced == 0


async def test_a_reachable_but_empty_catalog_is_filled(monkeypatch: pytest.MonkeyPatch) -> None:
    """A genuine first run: the rows are not there, so fetch them."""

    async def empty(_: object) -> list[Instrument]:
        return []

    async def sync(_: object) -> None:
        registry.install([instrument()])

    monkeypatch.setattr(catalog_runtime, "_read_catalog", empty)
    monkeypatch.setattr(catalog_runtime, "sync_once", sync)

    loaded = await catalog_runtime.ensure_registry(NO_CONTAINER, stop=asyncio.Event())

    assert loaded == 1
