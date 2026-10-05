"""Auth cookies.

The browser gets its tokens as httpOnly cookies so that a script injected into
the terminal cannot read them. That reintroduces CSRF, which the double-submit
token below addresses: the CSRF value is set in a readable cookie and must be
echoed in a header, something a cross-site form cannot do.

Non-browser clients ignore all of this and send ``Authorization: Bearer``.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime

from fastapi import Request, Response

from chartnexus.bootstrap.settings import AuthSettings, SecuritySettings
from chartnexus.contexts.identity.application.dto import TokenPair

CSRF_HEADER = "X-CSRF-Token"


@dataclass(frozen=True, slots=True)
class CookieManager:
    auth: AuthSettings
    security: SecuritySettings

    def issue(self, response: Response, tokens: TokenPair, *, now: datetime) -> str:
        """Set all three cookies and return the CSRF token."""
        access_max_age = _seconds_until(tokens.access_token_expires_at, now)
        refresh_max_age = _seconds_until(tokens.refresh_token_expires_at, now)

        self._set(
            response,
            name=self.auth.access_cookie_name,
            value=tokens.access_token,
            max_age=access_max_age,
            http_only=True,
            path="/",
        )
        self._set(
            response,
            name=self.auth.refresh_cookie_name,
            value=tokens.refresh_token,
            max_age=refresh_max_age,
            http_only=True,
            # Scoped to the auth routes: no other endpoint has any use for it,
            # so no other endpoint can leak it.
            path=self.auth.refresh_cookie_path,
        )

        csrf_token = secrets.token_urlsafe(32)
        self._set(
            response,
            name=self.auth.csrf_cookie_name,
            value=csrf_token,
            max_age=refresh_max_age,
            # Readable by design — the client has to copy it into a header.
            http_only=False,
            path="/",
        )
        return csrf_token

    def clear(self, response: Response) -> None:
        for name, path in (
            (self.auth.access_cookie_name, "/"),
            (self.auth.refresh_cookie_name, self.auth.refresh_cookie_path),
            (self.auth.csrf_cookie_name, "/"),
        ):
            response.delete_cookie(
                key=name,
                path=path,
                domain=self.security.cookie_domain,
                secure=self.security.cookie_secure,
                httponly=name != self.auth.csrf_cookie_name,
                samesite=self.security.cookie_samesite,
            )

    def read_access_token(self, request: Request) -> str | None:
        return request.cookies.get(self.auth.access_cookie_name)

    def read_refresh_token(self, request: Request) -> str | None:
        return request.cookies.get(self.auth.refresh_cookie_name)

    def verify_csrf(self, request: Request) -> bool:
        """Double-submit check, applied only to cookie-authenticated requests.

        A Bearer caller never sends the cookie, so there is nothing for a third
        party site to ride on and the check does not apply.
        """
        cookie_value = request.cookies.get(self.auth.csrf_cookie_name)
        if cookie_value is None:
            return False
        header_value = request.headers.get(CSRF_HEADER)
        if not header_value:
            return False
        return secrets.compare_digest(cookie_value, header_value)

    def _set(
        self,
        response: Response,
        *,
        name: str,
        value: str,
        max_age: int,
        http_only: bool,
        path: str,
    ) -> None:
        response.set_cookie(
            key=name,
            value=value,
            max_age=max_age,
            path=path,
            domain=self.security.cookie_domain,
            secure=self.security.cookie_secure,
            httponly=http_only,
            samesite=self.security.cookie_samesite,
        )


def _seconds_until(moment: datetime, now: datetime) -> int:
    return max(0, int((moment - now).total_seconds()))
