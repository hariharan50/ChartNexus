"""The hardening headers every response carries.

These matter most for the thing they are easy to get wrong: the strict JSON
content policy must not reach an HTML page, because ``default-src 'none'``
plus ``sandbox`` renders Swagger UI blank with nothing in the response to
explain why. HSTS is the mirror case — correct when deployed, and a developer's
browser pinned to ``https://localhost`` when not.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from chartnexus.infrastructure.transport.http.middleware import SecurityHeadersMiddleware

pytestmark = pytest.mark.unit


def client(*, hsts: bool) -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, hsts=hsts)

    @app.get("/json")
    async def json_route() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/page", response_class=HTMLResponse)
    async def html_route() -> HTMLResponse:
        return HTMLResponse("<p>docs</p>")

    return TestClient(app)


class TestEveryResponse:
    def test_the_baseline_headers_are_present(self) -> None:
        response = client(hsts=False).get("/json")

        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["cross-origin-opener-policy"] == "same-origin"
        assert response.headers["cross-origin-resource-policy"] == "same-origin"
        assert "geolocation=()" in response.headers["permissions-policy"]

    def test_a_header_is_set_once_not_appended(self) -> None:
        # Two layers both setting a policy is normal (app and edge proxy); a
        # browser given `DENY, DENY` treats the whole value as unparseable.
        response = client(hsts=False).get("/json")

        assert response.headers["x-frame-options"] == "DENY"


class TestContentPolicy:
    def test_json_gets_the_strict_policy(self) -> None:
        response = client(hsts=False).get("/json")

        assert response.headers["content-security-policy"] == (
            "default-src 'none'; frame-ancestors 'none'; sandbox"
        )

    def test_html_is_left_alone(self) -> None:
        response = client(hsts=False).get("/page")

        assert "content-security-policy" not in response.headers
        # The rest still applies — only the policy written for JSON is skipped.
        assert response.headers["x-frame-options"] == "DENY"


class TestStrictTransportSecurity:
    def test_deployed_environments_send_it(self) -> None:
        response = client(hsts=True).get("/json")

        assert response.headers["strict-transport-security"] == (
            "max-age=63072000; includeSubDomains; preload"
        )

    def test_local_development_does_not(self) -> None:
        response = client(hsts=False).get("/json")

        assert "strict-transport-security" not in response.headers
