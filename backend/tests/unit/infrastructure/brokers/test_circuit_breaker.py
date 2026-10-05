"""The breaker's one important distinction: down versus saying no.

One breaker is shared by every instrument under a tenant's broker app. That is
only safe because a *rejection* — the broker answering "no such symbol" — does
not count toward opening it. Were that not so, a single delisted ticker in a
219-instrument board would take the whole tenant's market data offline for
everyone, which is exactly the failure this test exists to prevent.
"""

from __future__ import annotations

import pytest

from chartnexus.contexts.broker_connections.domain.errors import (
    BrokerRejectedError,
    BrokerUnavailableError,
)
from chartnexus.infrastructure.brokers.fyers.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)

pytestmark = pytest.mark.unit


async def _ok() -> str:
    return "payload"


async def _rejected() -> str:
    raise BrokerRejectedError("no such symbol")


async def _unavailable() -> str:
    raise BrokerUnavailableError


async def test_a_rejection_never_opens_the_circuit() -> None:
    """A bad symbol says the broker is up and answering."""
    breaker = CircuitBreaker(failure_threshold=2)

    for _ in range(10):
        with pytest.raises(BrokerRejectedError):
            await breaker.call(_rejected)

    assert breaker.state is CircuitState.CLOSED
    assert await breaker.call(_ok) == "payload"


async def test_repeated_unavailability_opens_the_circuit() -> None:
    breaker = CircuitBreaker(failure_threshold=3)

    for _ in range(3):
        with pytest.raises(BrokerUnavailableError):
            await breaker.call(_unavailable)

    assert breaker.state is CircuitState.OPEN


async def test_an_open_circuit_fails_without_calling_the_broker() -> None:
    """The point of opening: stop spending the request budget and the latency."""
    breaker = CircuitBreaker(failure_threshold=1)
    with pytest.raises(BrokerUnavailableError):
        await breaker.call(_unavailable)

    called = False

    async def _probe() -> str:
        nonlocal called
        called = True
        return "never"

    with pytest.raises(BrokerUnavailableError):
        await breaker.call(_probe)

    assert not called


async def test_a_success_before_the_threshold_clears_the_count() -> None:
    """Intermittent failures must not accumulate into an outage verdict."""
    breaker = CircuitBreaker(failure_threshold=3)

    with pytest.raises(BrokerUnavailableError):
        await breaker.call(_unavailable)
    await breaker.call(_ok)
    for _ in range(2):
        with pytest.raises(BrokerUnavailableError):
            await breaker.call(_unavailable)

    assert breaker.state is CircuitState.CLOSED


async def test_the_circuit_half_opens_once_the_reset_window_passes() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_after_seconds=0)

    with pytest.raises(BrokerUnavailableError):
        await breaker.call(_unavailable)

    assert breaker.state is CircuitState.HALF_OPEN
    # Half-open lets one request through, and a success closes it.
    assert await breaker.call(_ok) == "payload"
    assert breaker.state is CircuitState.CLOSED
