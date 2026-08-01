"""Ports the identity use cases depend on.

Protocols rather than ABCs: the adapters live in ``infrastructure`` and must not
be imported here, and a test double only has to match the shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from marketcompass.contexts.identity.domain.refresh_session import (
    RefreshSession,
    SessionRevocationReason,
)
from marketcompass.contexts.identity.domain.user import User
from marketcompass.contexts.identity.domain.value_objects import EmailAddress
from marketcompass.shared_kernel.types.identifiers import SessionId, TenantId, UserId


@runtime_checkable
class UserRepository(Protocol):
    async def get(self, user_id: UserId) -> User | None: ...

    async def find_by_email(self, email: EmailAddress) -> User | None: ...

    async def find_by_google_subject(self, subject: str) -> User | None: ...

    async def add(self, user: User) -> None: ...

    async def update(self, user: User) -> None: ...

    async def email_exists(self, email: EmailAddress) -> bool: ...


@runtime_checkable
class RefreshSessionRepository(Protocol):
    async def get(self, session_id: SessionId) -> RefreshSession | None: ...

    async def find_by_token_hash(self, token_hash: str) -> RefreshSession | None: ...

    async def add(self, session: RefreshSession) -> None: ...

    async def update(self, session: RefreshSession) -> None: ...

    async def list_active_for_user(self, user_id: UserId) -> list[RefreshSession]: ...

    async def revoke_family(
        self,
        family_id: SessionId,
        reason: SessionRevocationReason,
        now: datetime,
    ) -> int:
        """Revoke every session in a family. Returns how many were revoked."""
        ...

    async def revoke_all_for_user(
        self,
        user_id: UserId,
        reason: SessionRevocationReason,
        now: datetime,
        *,
        except_session_id: SessionId | None = None,
    ) -> int: ...


@runtime_checkable
class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...

    def needs_rehash(self, password_hash: str) -> bool:
        """True when the hash used weaker parameters than the current policy."""
        ...

    def dummy_verify(self) -> None:
        """Burn the same CPU as a real verification.

        Called when no user matched, so that response time does not reveal
        whether an account exists.
        """
        ...


@dataclass(frozen=True, slots=True)
class AccessToken:
    value: str
    expires_at: datetime
    expires_in_seconds: int
    jti: str


@runtime_checkable
class AccessTokenIssuer(Protocol):
    def issue(
        self,
        *,
        user_id: UserId,
        tenant_id: TenantId,
        session_id: SessionId,
        roles: frozenset[str],
        email: str,
        now: datetime,
    ) -> AccessToken: ...

    def decode(self, token: str) -> AccessTokenClaims: ...


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    subject: UserId
    tenant_id: TenantId
    session_id: SessionId
    email: str
    roles: frozenset[str]
    issued_at: datetime
    expires_at: datetime
    jti: str


@dataclass(frozen=True, slots=True)
class GoogleProfile:
    """The subset of Google's id_token claims this application trusts."""

    subject: str
    email: EmailAddress
    email_verified: bool
    display_name: str
    picture_url: str | None
    hosted_domain: str | None


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    authorization_url: str
    state: str
    code_verifier: str
    nonce: str


@runtime_checkable
class GoogleIdentityProvider(Protocol):
    def build_authorization_request(
        self, *, redirect_uri: str | None = None
    ) -> AuthorizationRequest: ...

    async def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        nonce: str,
        redirect_uri: str | None = None,
    ) -> GoogleProfile:
        """Trade an authorization code for a verified profile.

        Implementations must validate the id_token signature, issuer, audience,
        expiry, and nonce before returning.
        """
        ...


@runtime_checkable
class OAuthStateStore(Protocol):
    """Short-lived storage for in-flight authorization requests."""

    async def save(
        self,
        state: str,
        *,
        code_verifier: str,
        nonce: str,
        redirect_to: str | None,
        ttl_seconds: int,
    ) -> None: ...

    async def consume(self, state: str) -> PendingAuthorization | None:
        """Fetch and delete in one step, so a state can only be used once."""
        ...


@dataclass(frozen=True, slots=True)
class PendingAuthorization:
    code_verifier: str
    nonce: str
    redirect_to: str | None


@runtime_checkable
class LoginRateLimiter(Protocol):
    async def check(self, key: str) -> None:
        """Raise :class:`RateLimitError` when the caller is over budget."""
        ...

    async def record_failure(self, key: str) -> None: ...

    async def reset(self, key: str) -> None: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class UnitOfWork(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
