"""In-memory doubles for the identity ports.

Real enough to exercise the use cases (they enforce the same uniqueness rules
the database does) without needing Postgres or Redis in a unit test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from chartnexus.bootstrap.settings import AuthSettings, SecuritySettings
from chartnexus.contexts.identity.application.ports import (
    AuthorizationRequest,
    GoogleProfile,
    PendingAuthorization,
)
from chartnexus.contexts.identity.domain.refresh_session import (
    RefreshSession,
    SessionRevocationReason,
)
from chartnexus.contexts.identity.domain.user import User
from chartnexus.contexts.identity.domain.value_objects import (
    AuthProvider,
    EmailAddress,
    PhoneNumber,
)
from chartnexus.infrastructure.time.clock import FixedClock
from chartnexus.shared_kernel.domain.errors import RateLimitError
from chartnexus.shared_kernel.types.identifiers import SessionId, UserId

START = datetime(2026, 8, 1, 9, 30, tzinfo=UTC)


@dataclass
class FakeUserRepository:
    users: dict[UserId, User] = field(default_factory=dict)

    async def get(self, user_id: UserId) -> User | None:
        return self.users.get(user_id)

    async def find_by_email(self, email: EmailAddress) -> User | None:
        return next((u for u in self.users.values() if u.email == email), None)

    async def find_by_phone(self, phone: PhoneNumber) -> User | None:
        return next((u for u in self.users.values() if u.phone == phone), None)

    async def find_by_google_subject(self, subject: str) -> User | None:
        for user in self.users.values():
            identity = user.identity_for(AuthProvider.GOOGLE)
            if identity and identity.subject == subject:
                return user
        return None

    async def email_exists(self, email: EmailAddress) -> bool:
        return await self.find_by_email(email) is not None

    async def phone_exists(self, phone: PhoneNumber) -> bool:
        return await self.find_by_phone(phone) is not None

    async def add(self, user: User) -> None:
        if await self.email_exists(user.email):
            msg = "unique violation on users.email"
            raise ValueError(msg)
        if user.phone is not None and await self.phone_exists(user.phone):
            msg = "unique violation on users.phone"
            raise ValueError(msg)
        self.users[user.id] = user

    async def update(self, user: User) -> None:
        self.users[user.id] = user


@dataclass
class FakeSessionRepository:
    # The real repository evaluates "is this session still active" against the
    # database's clock. This fake has to be told the time, because the suite
    # issues its sessions at a pinned START date: reading the wall clock here
    # measured a fake session's lifetime against today, so every session aged
    # out the moment real time passed START + the refresh TTL and
    # `list_active_for_user` silently began returning nothing.
    clock: FixedClock
    sessions: dict[SessionId, RefreshSession] = field(default_factory=dict)

    async def get(self, session_id: SessionId) -> RefreshSession | None:
        return self.sessions.get(session_id)

    async def find_by_token_hash(self, token_hash: str) -> RefreshSession | None:
        return next(
            (s for s in self.sessions.values() if s.token_hash == token_hash),
            None,
        )

    async def add(self, session: RefreshSession) -> None:
        self.sessions[session.id] = session

    async def update(self, session: RefreshSession) -> None:
        self.sessions[session.id] = session

    async def list_active_for_user(self, user_id: UserId) -> list[RefreshSession]:
        now = self.clock.now()
        return [s for s in self.sessions.values() if s.user_id == user_id and s.is_active(now)]

    async def revoke_family(
        self, family_id: SessionId, reason: SessionRevocationReason, now: datetime
    ) -> int:
        revoked = 0
        for session in self.sessions.values():
            if session.family_id == family_id and not session.is_revoked:
                session.revoke(reason, now)
                revoked += 1
        return revoked

    async def revoke_all_for_user(
        self,
        user_id: UserId,
        reason: SessionRevocationReason,
        now: datetime,
        *,
        except_session_id: SessionId | None = None,
    ) -> int:
        revoked = 0
        for session in self.sessions.values():
            if session.user_id == user_id and not session.is_revoked:
                if except_session_id and session.id == except_session_id:
                    continue
                session.revoke(reason, now)
                revoked += 1
        return revoked


class FakeHasher:
    """Deterministic and instant. Cost parameters are Argon2's problem."""

    def __init__(self) -> None:
        self.dummy_verifications = 0

    def hash(self, password: str) -> str:
        return f"hashed::{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed::{password}"

    def needs_rehash(self, password_hash: str) -> bool:
        return password_hash.startswith("legacy::")

    def dummy_verify(self) -> None:
        self.dummy_verifications += 1


@dataclass
class FakeUnitOfWork:
    commits: int = 0
    rollbacks: int = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


@dataclass
class FakeRateLimiter:
    failures: dict[str, int] = field(default_factory=dict)
    limit: int = 100

    async def check(self, key: str) -> None:
        if self.failures.get(key, 0) >= self.limit:
            raise RateLimitError("too many attempts", retry_after_seconds=60)

    async def record_failure(self, key: str) -> None:
        self.failures[key] = self.failures.get(key, 0) + 1

    async def reset(self, key: str) -> None:
        self.failures.pop(key, None)


@dataclass
class FakeStateStore:
    entries: dict[str, PendingAuthorization] = field(default_factory=dict)

    async def save(
        self,
        state: str,
        *,
        code_verifier: str,
        nonce: str,
        redirect_to: str | None,
        ttl_seconds: int,
    ) -> None:
        self.entries[state] = PendingAuthorization(
            code_verifier=code_verifier, nonce=nonce, redirect_to=redirect_to
        )

    async def consume(self, state: str) -> PendingAuthorization | None:
        return self.entries.pop(state, None)


@dataclass
class FakeGoogleProvider:
    profile: GoogleProfile | None = None
    exchanges: int = 0

    def build_authorization_request(
        self, *, redirect_uri: str | None = None
    ) -> AuthorizationRequest:
        return AuthorizationRequest(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth?client_id=test",
            state="test-state",
            code_verifier="test-verifier",
            nonce="test-nonce",
        )

    async def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        nonce: str,
        redirect_uri: str | None = None,
    ) -> GoogleProfile:
        self.exchanges += 1
        assert self.profile is not None
        return self.profile


@pytest.fixture
def auth_settings() -> AuthSettings:
    return AuthSettings(jwt_signing_key="unit-test-signing-key-long-enough-for-hs256")


@pytest.fixture
def security_settings() -> SecuritySettings:
    return SecuritySettings()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(START)


@pytest.fixture
def users() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def sessions_repo(clock: FixedClock) -> FakeSessionRepository:
    return FakeSessionRepository(clock)


@pytest.fixture
def hasher() -> FakeHasher:
    return FakeHasher()


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def rate_limiter() -> FakeRateLimiter:
    return FakeRateLimiter()


def google_profile(
    *,
    subject: str = "google-subject-1",
    email: str = "person@example.com",
    verified: bool = True,
    hosted_domain: str | None = None,
) -> GoogleProfile:
    return GoogleProfile(
        subject=subject,
        email=EmailAddress.parse(email),
        email_verified=verified,
        display_name="Test Person",
        picture_url=None,
        hosted_domain=hosted_domain,
    )
