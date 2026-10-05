"""Isolation for the process-lived last-good stores.

``LastGood`` is shared by every request in a process on purpose - the services
are assembled per request, so a per-instance store could never actually hold
anything and the degrade ladder's last-good rung never fired. The same
lifetime makes it leak between tests: one test's successful fetch becomes the
next one's "a real quote was seen earlier", and a test asserting the mock
fallback silently stops testing it.

So every test here gets empty stores.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from chartnexus.contexts.market_data.application import queries


@pytest.fixture(autouse=True)
def _empty_last_good_stores() -> Iterator[None]:
    names = (
        "_SPOT_LAST_GOOD",
        "_FUTURES_LAST_GOOD",
        "_CHAIN_LAST_GOOD",
        "_HISTORY_LAST_GOOD",
    )
    saved = {name: getattr(queries, name) for name in names}
    for name in names:
        setattr(queries, name, queries.LastGood())
    yield
    for name, store in saved.items():
        setattr(queries, name, store)
