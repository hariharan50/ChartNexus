"""Every failure leaves the API as the same problem document."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from chartnexus.infrastructure.transport.http.exception_handlers import (
    PROBLEM_CONTENT_TYPE,
    register_exception_handlers,
)
from chartnexus.infrastructure.transport.http.request_id import RequestIdMiddleware
from chartnexus.shared_kernel.domain.errors import (
    EntitlementError,
    NotFoundError,
    RateLimitError,
    UpstreamError,
)

pytestmark = pytest.mark.unit


class _Credentials(BaseModel):
    email: str
    password: str


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError("instrument", "NIFTY24DEC")

    @app.get("/gated")
    async def gated() -> None:
        raise EntitlementError("gamma_exposure", required_plan="pro")

    @app.get("/throttled")
    async def throttled() -> None:
        raise RateLimitError("too many requests", retry_after_seconds=30)

    @app.get("/broker")
    async def broker() -> None:
        raise UpstreamError("fyers", "socket closed")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("connection string is postgres://user:hunter2@host")

    @app.post("/login")
    async def login(_credentials: _Credentials) -> None:
        return None

    return TestClient(app, raise_server_exceptions=False)


def test_not_found_maps_to_404_problem(client: TestClient) -> None:
    response = client.get("/missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_CONTENT_TYPE)
    body = response.json()
    assert body["code"] == "not_found"
    assert body["resource"] == "instrument"
    assert body["request_id"] == response.headers["x-request-id"]


def test_entitlement_failure_is_402_not_403(client: TestClient) -> None:
    """403 tells the user to ask an admin; 402 tells them to upgrade."""
    response = client.get("/gated")

    assert response.status_code == 402
    assert response.json()["required_plan"] == "pro"


def test_rate_limit_sets_retry_after(client: TestClient) -> None:
    response = client.get("/throttled")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"


def test_upstream_failure_is_502(client: TestClient) -> None:
    assert client.get("/broker").status_code == 502


def test_internal_detail_is_not_leaked(client: TestClient) -> None:
    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json()["detail"] == "An unexpected error occurred."
    assert "hunter2" not in response.text


def test_validation_errors_do_not_echo_the_submitted_password(client: TestClient) -> None:
    response = client.post("/login", json={"email": "a@b.com", "password": 12345})

    assert response.status_code == 422
    assert "12345" not in response.text
    assert response.json()["errors"][0]["field"] == "password"


def test_inbound_request_id_is_honoured_when_well_formed(client: TestClient) -> None:
    response = client.get("/missing", headers={"X-Request-ID": "edge-proxy-0123456789"})
    assert response.headers["x-request-id"] == "edge-proxy-0123456789"


def test_hostile_request_id_is_replaced(client: TestClient) -> None:
    """An unvalidated header would land verbatim in the logs."""
    response = client.get("/missing", headers={"X-Request-ID": "a b\nnewline-injection"})
    assert response.headers["x-request-id"] != "a b\nnewline-injection"
