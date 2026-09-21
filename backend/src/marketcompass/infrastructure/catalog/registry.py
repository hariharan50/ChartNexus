"""The catalog, in memory, for code that cannot await a database.

Three places need an instrument's reference row deep inside a synchronous call
stack: the FYERS symbol mapper, the futures-contract builder, and the mock
generator. Threading a repository through all of them would mean making a dozen
pure functions async to look up data that changes once a day.

So the catalog is cached per process. It is loaded at startup and refreshed by
the catalog worker after each sync. This is global state, which is worth being
uncomfortable about — it is justified here because the contents are immutable
reference data with a daily refresh cycle, and it is kept honest by being
explicit: :func:`install` and :func:`reset` are the only ways in, and tests use
:func:`installed` to scope a registry to one test.

An unknown symbol raises rather than falling back to a default. Inventing
plausible numbers for an instrument that does not exist is precisely the bug
this whole change was meant to remove.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from marketcompass.contexts.instrument_catalog.domain.instrument import (
    Instrument,
    InstrumentKind,
)
from marketcompass.shared_kernel.domain.errors import ValidationError


class InstrumentRegistry:
    """An immutable snapshot of the catalog."""

    __slots__ = ("_by_symbol",)

    def __init__(self, instruments: Iterable[Instrument] = ()) -> None:
        self._by_symbol: dict[str, Instrument] = {i.symbol: i for i in instruments}

    def __len__(self) -> int:
        return len(self._by_symbol)

    def __contains__(self, symbol: object) -> bool:
        return str(symbol).strip().upper() in self._by_symbol

    def get(self, symbol: str) -> Instrument:
        """The row for ``symbol``.

        Raises ``ValidationError`` — which the transport layer maps to a 422 —
        rather than ``KeyError``, because an unknown instrument is a bad
        request, not a bug.
        """
        instrument = self.find(symbol)
        if instrument is None:
            raise ValidationError(
                f"{str(symbol).strip().upper()} is not a tradeable instrument.",
                field="instrument",
            )
        return instrument

    def find(self, symbol: str) -> Instrument | None:
        return self._by_symbol.get(str(symbol).strip().upper())

    def symbols(self, *, kind: InstrumentKind | None = None) -> tuple[str, ...]:
        """Symbols, indices first then alphabetical — the order to iterate in
        when a worker covers "the universe"."""
        rows = [row for row in self._by_symbol.values() if kind is None or row.kind is kind]
        return tuple(row.symbol for row in sorted(rows, key=lambda r: (r.kind.value, r.symbol)))

    def all(self) -> tuple[Instrument, ...]:
        return tuple(self._by_symbol.values())


class _Slot:
    """Holds the live registry.

    A class attribute rather than a module global so that rebinding it is an
    ordinary assignment — no ``global`` statement, and one obvious place to
    look for what the process currently believes the universe is.
    """

    registry: InstrumentRegistry = InstrumentRegistry()


def current() -> InstrumentRegistry:
    return _Slot.registry


def install(instruments: Iterable[Instrument]) -> InstrumentRegistry:
    """Replace the process registry. Called at startup and after each sync."""
    _Slot.registry = InstrumentRegistry(instruments)
    return _Slot.registry


def reset() -> None:
    """Empty the registry. For tests, and for nothing else."""
    install(())


@contextmanager
def installed(instruments: Iterable[Instrument]) -> Iterator[InstrumentRegistry]:
    """Scope a registry to a block, restoring whatever was there before."""
    previous = _Slot.registry
    try:
        yield install(instruments)
    finally:
        _Slot.registry = previous
