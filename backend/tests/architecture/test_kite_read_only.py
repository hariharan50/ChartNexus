"""The Kite adapter reads market data and nothing else (ADR 0002).

ChartNexus holds a tenant's Kite session, and that session can place orders.
The promise ADR 0001 made for Fyers — read-only, always — is kept for Kite by
making sure no order, portfolio, margin or GTT path is ever spelled out in the
adapter. Cheap to check and hard to get round by accident.
"""

from __future__ import annotations

import re

import pytest

from tests.architecture.conftest import SRC

pytestmark = pytest.mark.architecture

KITE = SRC / "infrastructure" / "brokers" / "kite"

#: Kite Connect's mutating and account endpoints, and the SDK's verbs for them.
FORBIDDEN = re.compile(
    r"/orders|/portfolio|/margins|/gtt|/alerts|/mf/|/trades"
    r"|place_order|modify_order|cancel_order|place_gtt|convert_position",
    re.IGNORECASE,
)


def test_the_kite_adapter_exists() -> None:
    # Guards the guard: a moved folder would make the test below vacuous.
    assert KITE.is_dir()
    assert any(KITE.glob("*.py"))


def test_the_kite_adapter_has_no_order_or_portfolio_paths() -> None:
    violations = [
        f"{path.relative_to(SRC).as_posix()}:{number}: {line.strip()}"
        for path in sorted(KITE.rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if FORBIDDEN.search(line)
    ]

    if violations:
        listing = "\n  ".join(violations)
        pytest.fail(
            f"The Kite adapter is market-data only; found:\n  {listing}",
            pytrace=False,
        )
