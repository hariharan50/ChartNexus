"""Google OAuth 2.0 / OpenID Connect adapter.

Implements the ``GoogleIdentityProvider`` port using the Authorization Code
flow with PKCE. The id_token is verified locally against Google's published JWKS
— the ``tokeninfo`` endpoint is not used, because trusting a remote answer about
a token's validity adds a network dependency to every login for no security gain.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt.exceptions import InvalidTokenError

from chartnexus.bootstrap.settings import GoogleOAuthSettings
from chartnexus.contexts.identity.application.ports import (
    AuthorizationRequest,
    GoogleProfile,
)
from chartnexus.contexts.identity.domain.errors import OAuthProviderError
from chartnexus.contexts.identity.domain.value_objects import EmailAddress


@dataclass(slots=True)
class _CachedJwks:
    keys: dict[str, Any]
    fetched_at: float


class GoogleOAuthClient:
    def __init__(self, settings: GoogleOAuthSettings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http
        self._jwks: _CachedJwks | None = None

    # -- step 1: authorization URL -----------------------------------------

    def build_authorization_request(
        self, *, redirect_uri: str | None = None
    ) -> AuthorizationRequest:
        code_verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)

        parameters = {
            "client_id": self._settings.client_id,
            "redirect_uri": redirect_uri or self._settings.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self._settings.scopes),
            "state": state,
            "nonce": nonce,
            "code_challenge": _s256_challenge(code_verifier),
            "code_challenge_method": "S256",
            # Forces the account chooser, so a shared machine does not silently
            # sign in as whoever used it last.
            "prompt": "select_account",
            "access_type": "online",
        }
        if self._settings.allowed_hosted_domains:
            parameters["hd"] = self._settings.allowed_hosted_domains[0]

        return AuthorizationRequest(
            authorization_url=f"{self._settings.authorization_endpoint}?{urlencode(parameters)}",
            state=state,
            code_verifier=code_verifier,
            nonce=nonce,
        )

    # -- step 2: code exchange ---------------------------------------------

    async def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        nonce: str,
        redirect_uri: str | None = None,
    ) -> GoogleProfile:
        try:
            response = await self._http.post(
                self._settings.token_endpoint,
                data={
                    "code": code,
                    "client_id": self._settings.client_id,
                    "client_secret": self._settings.client_secret.get_secret_value(),
                    "redirect_uri": redirect_uri or self._settings.redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                },
                headers={"Accept": "application/json"},
                timeout=self._settings.request_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise OAuthProviderError("Could not reach Google to complete sign-in.") from exc

        if response.status_code != httpx.codes.OK:
            # Google's error body names the cause (bad verifier, reused code);
            # it is useful in logs but must not reach the user.
            raise OAuthProviderError("Google rejected this sign-in attempt.")

        payload = response.json()
        id_token = payload.get("id_token")
        if not id_token:
            raise OAuthProviderError("Google did not return an identity token.")

        claims = await self._verify_id_token(id_token, nonce=nonce)
        return _to_profile(claims)

    # -- id_token verification ---------------------------------------------

    async def _verify_id_token(self, id_token: str, *, nonce: str) -> dict[str, Any]:
        key = await self._signing_key_for(id_token)
        try:
            claims: dict[str, Any] = jwt.decode(
                id_token,
                key=key,
                algorithms=["RS256"],
                audience=self._settings.client_id,
                options={
                    "require": ["exp", "iat", "aud", "iss", "sub"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": True,
                },
            )
        except InvalidTokenError as exc:
            raise OAuthProviderError("Google's identity token failed verification.") from exc

        if claims.get("iss") not in self._settings.issuers:
            raise OAuthProviderError("Google's identity token has an unexpected issuer.")

        # Binds this token to the authorization request we started; without it a
        # token obtained elsewhere could be replayed into our callback.
        if claims.get("nonce") != nonce:
            raise OAuthProviderError("This sign-in could not be matched to its request.")

        return claims

    async def _signing_key_for(self, id_token: str) -> Any:
        try:
            key_id = jwt.get_unverified_header(id_token).get("kid")
        except InvalidTokenError as exc:
            raise OAuthProviderError("Google's identity token is malformed.") from exc
        if not key_id:
            raise OAuthProviderError("Google's identity token has no key id.")

        keys = await self._load_jwks()
        if key_id not in keys:
            # Google rotates keys; a miss usually means our cache is stale.
            keys = await self._load_jwks(force=True)
        key_data = keys.get(key_id)
        if key_data is None:
            raise OAuthProviderError("Google's signing key could not be found.")

        return jwt.PyJWK(key_data).key

    async def _load_jwks(self, *, force: bool = False) -> dict[str, Any]:
        cached = self._jwks
        if (
            not force
            and cached is not None
            and time.monotonic() - cached.fetched_at < self._settings.jwks_cache_seconds
        ):
            return cached.keys

        try:
            response = await self._http.get(
                self._settings.jwks_uri,
                timeout=self._settings.request_timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            if cached is not None:
                # Serving from a stale cache beats failing every login while
                # Google's endpoint is briefly unreachable.
                return cached.keys
            raise OAuthProviderError("Could not fetch Google's signing keys.") from exc

        keys = {key["kid"]: key for key in response.json().get("keys", []) if "kid" in key}
        self._jwks = _CachedJwks(keys=keys, fetched_at=time.monotonic())
        return keys


def _to_profile(claims: dict[str, Any]) -> GoogleProfile:
    email_claim = claims.get("email")
    if not email_claim:
        raise OAuthProviderError("This Google account did not share an email address.")

    return GoogleProfile(
        subject=str(claims["sub"]),
        email=EmailAddress.parse(str(email_claim)),
        # Google sends this as a bool or the string "true" depending on the flow.
        email_verified=str(claims.get("email_verified", "false")).lower() == "true",
        display_name=str(claims.get("name") or "").strip(),
        picture_url=str(claims["picture"]) if claims.get("picture") else None,
        hosted_domain=str(claims["hd"]) if claims.get("hd") else None,
    )


def _s256_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
