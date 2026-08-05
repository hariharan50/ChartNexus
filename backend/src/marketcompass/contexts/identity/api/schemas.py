"""Request and response models for the auth endpoints.

These are the wire contract. They deliberately do not mirror the domain: the
API never exposes a password hash, a token hash, or the internal tenant of
another user.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from marketcompass.contexts.identity.application.dto import (
    AuthenticationResult,
    SessionView,
    UserView,
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- requests --------------------------------------------------------------


class RegisterRequest(_Schema):
    email: EmailStr = Field(examples=["analyst@example.com"])
    # Bounded here as well as in the domain so an oversized body is rejected
    # before it ever reaches Argon2.
    password: str = Field(min_length=8, max_length=256, examples=["correct-horse-battery"])
    # Loosely bounded on purpose: the domain's PhoneNumber owns the real rules,
    # and it accepts several spellings ("+91 98765 43210") that a tight length
    # here would reject before normalisation.
    phone: str = Field(min_length=10, max_length=20, examples=["9876543210"])
    display_name: str = Field(default="", max_length=120)


class LoginRequest(_Schema):
    """``identifier`` is an email address or a phone number.

    Deliberately not ``EmailStr``: that type cannot represent a phone number,
    and validating the format here would reject phone sign-in outright.
    """

    identifier: str = Field(
        min_length=3,
        max_length=254,
        examples=["analyst@example.com", "9876543210"],
    )
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(_Schema):
    """Body is optional — browsers send the refresh token as a cookie."""

    refresh_token: str | None = Field(default=None, max_length=512)


class LogoutRequest(_Schema):
    refresh_token: str | None = Field(default=None, max_length=512)


class GoogleAuthorizeRequest(_Schema):
    redirect_to: str | None = Field(
        default=None,
        max_length=512,
        description="Relative path to return to after sign-in. Absolute URLs are ignored.",
    )


class GoogleCallbackRequest(_Schema):
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=512)


# --- responses -------------------------------------------------------------


class UserResponse(_Schema):
    id: str
    email: str
    # Only ever the requester's own number: these endpoints return the caller's
    # profile, never another account's, so there is nothing to mask.
    phone: str | None
    display_name: str
    status: str
    roles: tuple[str, ...]
    email_verified: bool
    has_password: bool
    linked_providers: tuple[str, ...]
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def of(cls, user: UserView) -> UserResponse:
        return cls(
            id=str(user.id),
            email=user.email,
            phone=user.phone,
            display_name=user.display_name,
            status=user.status,
            roles=user.roles,
            email_verified=user.email_verified,
            has_password=user.has_password,
            linked_providers=user.linked_providers,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )


class TokenResponse(_Schema):
    """Tokens are also set as cookies; the body serves non-browser clients."""

    access_token: str
    token_type: str = "Bearer"  # noqa: S105 — scheme name
    expires_in: int
    refresh_token: str
    csrf_token: str


class AuthenticationResponse(_Schema):
    user: UserResponse
    tokens: TokenResponse
    is_new_user: bool = False

    @classmethod
    def of(cls, result: AuthenticationResult, *, csrf_token: str) -> AuthenticationResponse:
        return cls(
            user=UserResponse.of(result.user),
            tokens=TokenResponse(
                access_token=result.tokens.access_token,
                expires_in=result.tokens.access_token_expires_in,
                refresh_token=result.tokens.refresh_token,
                csrf_token=csrf_token,
            ),
            is_new_user=result.is_new_user,
        )


class GoogleAuthorizeResponse(_Schema):
    authorization_url: str
    state: str


class SessionResponse(_Schema):
    id: str
    created_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip_address: str | None
    is_current: bool

    @classmethod
    def of(cls, session: SessionView) -> SessionResponse:
        return cls(
            id=str(session.id),
            created_at=session.created_at,
            expires_at=session.expires_at,
            user_agent=session.user_agent,
            ip_address=session.ip_address,
            is_current=session.is_current,
        )


class MessageResponse(_Schema):
    message: str


class RevokedSessionsResponse(_Schema):
    revoked: int
