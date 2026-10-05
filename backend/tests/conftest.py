"""Test-suite-wide isolation.

Settings read ``backend/.env`` at construction time. Without this fixture a
developer's local file leaks into assertions, so the suite passes on their
machine and fails in CI (or worse, the reverse).

The instrument catalog needs the same treatment for the same reason. Adapters
resolve symbols through a process-level registry loaded from the database, so
a test that does not install one would either see an empty universe or — worse,
if the tests ever ran in one process after a real load — whatever the last test
left behind.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal

import pytest

from chartnexus.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)
from chartnexus.infrastructure.catalog import registry


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path_factory) -> Iterator[None]:  # type: ignore[no-untyped-def]
    for key in list(os.environ):
        if key.startswith("CN_"):
            monkeypatch.delenv(key, raising=False)

    # Settings resolve `.env` relative to the working directory; pointing that
    # at an empty directory removes the file without touching the developer's.
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))
    yield


def _index(
    symbol: str, root: str, *, lot: int, step: str, level: str, exchange: str = "NSE"
) -> Instrument:
    return Instrument(
        symbol=symbol,
        kind=InstrumentKind.INDEX,
        name=symbol,
        exchange=exchange,
        lot_size=lot,
        tick_size=Decimal("0.05"),
        spot_symbol=f"{exchange}:{root}-INDEX",
        futures_root=symbol,
        strike_step=Decimal(step),
        reference_price=Decimal(level),
    )


def _stock(symbol: str, *, lot: int, step: str, level: str) -> Instrument:
    return Instrument(
        symbol=symbol,
        kind=InstrumentKind.STOCK,
        name=f"{symbol} LIMITED",
        exchange="NSE",
        lot_size=lot,
        tick_size=Decimal("0.05"),
        spot_symbol=f"NSE:{symbol}-EQ",
        futures_root=symbol,
        isin="INE000A01000",
        strike_step=Decimal(step),
        reference_price=Decimal(level),
    )


# The three indices carry the exact lot sizes, strike steps and levels the
# mock generator used when they were hard-coded, so the simulation's existing
# assertions keep their meaning. The two stocks are there so a test can reach
# for one without rebuilding the fixture: ASHOKLEY has the fractional 2.5 step
# that broke integer assumptions, and M&M has the ampersand.
CATALOG_FIXTURE: tuple[Instrument, ...] = (
    _index("NIFTY", "NIFTY50", lot=75, step="50", level="24647"),
    _index("BANKNIFTY", "NIFTYBANK", lot=30, step="100", level="57951"),
    _index("SENSEX", "SENSEX", lot=20, step="100", level="78839", exchange="BSE"),
    _stock("RELIANCE", lot=500, step="10", level="1270"),
    _stock("ASHOKLEY", lot=5000, step="2.5", level="167.5"),
    _stock("M&M", lot=200, step="50", level="3000"),
)


@pytest.fixture(scope="session", autouse=True)
def instrument_catalog() -> Iterator[None]:
    """Install a known universe for the whole run.

    Session-scoped rather than per-test because module-scoped fixtures build
    their data during setup, before any function-scoped fixture has run — a
    per-test registry would be installed too late for them to see it. A test
    that needs a different universe scopes its own with
    ``registry.installed(...)``.
    """
    with registry.installed(CATALOG_FIXTURE):
        yield
