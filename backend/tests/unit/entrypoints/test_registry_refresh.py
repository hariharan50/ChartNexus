"""Keeping a running process's instrument registry in step with the catalog.

The gap these cover only exists in a deployed environment, which is why it
survived: locally the API runs the catalog loop in-process, so its registry is
refreshed as a side effect of the sync. Deployed, the catalog worker is a
separate process refreshing *its own* copy, and every other process held
whatever the single startup read happened to return — an empty registry on a
first deploy, and yesterday's lot sizes after a circular.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import cast

import pytest

from chartnexus.bootstrap.container import Container
from chartnexus.bootstrap.settings import CatalogSettings, Settings
from chartnexus.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)
from chartnexus.entrypoints import catalog_runtime
from chartnexus.infrastructure.catalog import registry

pytestmark = pytest.mark.unit

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


def settings_with(*, enabled: bool = True, refresh_seconds: float = 0.0) -> Settings:
    """Settings for the loop, with its steady interval collapsed to nothing.

    The field's 30s lower bound is a production guard — it stops someone
    pointing a per-second poll at the catalog — and none of the behaviour below
    depends on the number being large. ``model_copy(update=...)`` is the
    documented way past validation on a frozen model, and beats sleeping
    through a real interval once per test.
    """
    catalog = CatalogSettings(enabled=enabled).model_copy(
        update={"registry_refresh_seconds": refresh_seconds}
    )
    return Settings().model_copy(update={"catalog": catalog})


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """The loop is driven by its waits; the waiting itself is not the subject."""
    monkeypatch.setattr(catalog_runtime, "_RETRY_BASE_SECONDS", 0.0)
    monkeypatch.setattr(catalog_runtime, "_RETRY_CEILING_SECONDS", 0.0)


@pytest.fixture(autouse=True)
def _empty_registry() -> Iterator[None]:
    with registry.installed(()):
        yield


def reads_returning(
    *results: list[Instrument],
    stop: asyncio.Event,
) -> object:
    """A ``_read_catalog`` that walks ``results`` and then sets ``stop``.

    The loop is infinite by design, so a test ends it the way a SIGTERM would
    rather than by cancelling and inspecting the wreckage.
    """
    calls = 0

    async def read(_: object) -> list[Instrument]:
        nonlocal calls
        result = results[min(calls, len(results) - 1)]
        calls += 1
        if calls >= len(results):
            stop.set()
        return result

    return read


class TestAColdStart:
    async def test_an_empty_registry_is_filled_by_a_later_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The first-deploy case. Startup read nothing because the catalog
        worker had not synced yet; nothing used to try again."""
        stop = asyncio.Event()
        monkeypatch.setattr(
            catalog_runtime,
            "_read_catalog",
            reads_returning([], [instrument()], stop=stop),
        )

        await catalog_runtime.run_registry_refresh_loop(NO_CONTAINER, settings_with(), stop=stop)

        assert "NIFTY" in registry.current()

    async def test_a_database_that_is_not_up_yet_does_not_end_the_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stop = asyncio.Event()
        attempts = 0

        async def flaky(_: object) -> list[Instrument]:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ConnectionRefusedError("the database is still starting")
            stop.set()
            return [instrument()]

        monkeypatch.setattr(catalog_runtime, "_read_catalog", flaky)

        await catalog_runtime.run_registry_refresh_loop(NO_CONTAINER, settings_with(), stop=stop)

        assert attempts == 2
        assert "NIFTY" in registry.current()


class TestStayingCurrent:
    async def test_a_changed_catalog_replaces_the_cached_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """What a morning refresh looks like from a worker's side: the rows it
        reads are not the rows it holds."""
        stop = asyncio.Event()
        monkeypatch.setattr(
            catalog_runtime,
            "_read_catalog",
            reads_returning(
                [instrument("NIFTY")],
                [instrument("NIFTY"), instrument("BANKNIFTY")],
                stop=stop,
            ),
        )

        await catalog_runtime.run_registry_refresh_loop(NO_CONTAINER, settings_with(), stop=stop)

        assert "BANKNIFTY" in registry.current()

    async def test_it_never_syncs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Syncing is the catalog worker's job alone. Six processes each
        deciding to fetch the ~19 MB symbol masters would turn one cold start
        into a stampede against the rows they all read."""
        stop = asyncio.Event()
        syncs = 0

        async def sync(_: object) -> None:
            nonlocal syncs
            syncs += 1

        monkeypatch.setattr(catalog_runtime, "_read_catalog", reads_returning([], [], stop=stop))
        monkeypatch.setattr(catalog_runtime, "sync_once", sync)

        await catalog_runtime.run_registry_refresh_loop(NO_CONTAINER, settings_with(), stop=stop)

        assert syncs == 0


class TestWhenDisabled:
    async def test_it_returns_without_reading(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def never(_: object) -> list[Instrument]:
            raise AssertionError("the catalog was read with refreshing disabled")

        monkeypatch.setattr(catalog_runtime, "_read_catalog", never)

        await catalog_runtime.run_registry_refresh_loop(
            NO_CONTAINER, settings_with(enabled=False), stop=asyncio.Event()
        )


class TestTheWorkerHelper:
    async def test_the_refresh_task_is_cancelled_when_the_body_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A worker that dies must not leave the loop running behind it."""
        started = asyncio.Event()

        async def loop(*_: object, **__: object) -> None:
            started.set()
            await asyncio.Event().wait()  # never returns on its own

        monkeypatch.setattr(catalog_runtime, "run_registry_refresh_loop", loop)

        stop = asyncio.Event()
        with pytest.raises(RuntimeError, match="the worker fell over"):
            async with catalog_runtime.registry_kept_current(
                NO_CONTAINER, settings_with(), stop=stop
            ):
                await started.wait()
                raise RuntimeError("the worker fell over")

        # The context manager signals its own stop on the way out, so a loop
        # that checks the event (the real one does) winds down rather than
        # relying on the cancellation alone.
        assert stop.is_set()
