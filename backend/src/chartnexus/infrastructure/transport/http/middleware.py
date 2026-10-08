"""Response-hardening middleware.

The security headers a browser needs are set here rather than only at the edge
proxy: the API is reachable directly on the container network, and a header the
app itself emits cannot be lost by a misconfigured reverse proxy. nginx sets the
same family of headers for the HTML app it serves, and duplicates are harmless
because both layers overwrite rather than append.

Two exceptions to "every response gets everything":

``Strict-Transport-Security`` is only meaningful over HTTPS and would pin a
developer's browser to ``https://localhost``, so it is emitted for deployed
environments only.

The ``Content-Security-Policy`` below is written for JSON — ``default-src
'none'`` plus ``sandbox`` is right for a response nothing should be able to
execute, and wrong for an HTML page. The only HTML this process serves is the
Swagger UI at ``/docs``, which is disabled when deployed; rather than special-case
that path, the policy is skipped for any ``text/html`` response, so the header can
never be the reason a page renders blank.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Sent on every response, HTML included.
_BASE_HEADERS: tuple[tuple[str, str], ...] = (
    ("x-content-type-options", "nosniff"),
    ("x-frame-options", "DENY"),
    ("referrer-policy", "no-referrer"),
    ("cross-origin-opener-policy", "same-origin"),
    ("cross-origin-resource-policy", "same-origin"),
    ("permissions-policy", "geolocation=(), camera=(), microphone=(), payment=()"),
)

#: JSON-only. See the module docstring for why HTML is exempt.
_JSON_CSP = ("content-security-policy", "default-src 'none'; frame-ancestors 'none'; sandbox")

#: Two years, with subdomains, and preload-eligible. Deployed environments only.
_HSTS = ("strict-transport-security", "max-age=63072000; includeSubDomains; preload")


class SecurityHeadersMiddleware:
    """Adds the standard hardening headers to every HTTP response."""

    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self._headers = (*_BASE_HEADERS, _HSTS) if hsts else _BASE_HEADERS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self._headers:
                    # Overwrite rather than append: one route setting its own
                    # weaker policy must not survive into the response.
                    headers[name] = value
                if not headers.get("content-type", "").startswith("text/html"):
                    headers[_JSON_CSP[0]] = _JSON_CSP[1]
            await send(message)

        await self.app(scope, receive, send_with_headers)
