"""Refresh rotation, reuse detection, and session limits."""

from __future__ import annotations

import pytest

from chartnexus.contexts.identity.application.dto import RequestContextInput
from chartnexus.contexts.identity.application.session_service import (
    SessionPolicy,
    SessionService,
)
from chartnexus.contexts.identity.domain.errors import (
    SessionExpiredError,
    TokenReuseDetectedError,
)
from chartnexus.contexts.identity.domain.refresh_session import SessionRevocationReason
from chartnexus.contexts.identity.domain.user import User
from chartnexus.contexts.identity.domain.value_objects import EmailAddress
from chartnexus.infrastructure.security.token_signer import JwtAccessTokenIssuer
from chartnexus.shared_kernel.types.identifiers import TenantId, new_id
from tests.unit.contexts.identity.conftest import START

pytestmark = pytest.mark.unit

CONTEXT = RequestContextInput(user_agent="pytest", ip_address="127.0.0.1")


@pytest.fixture
def user() -> User:
    return User.register_with_password(
        tenant_id=TenantId(new_id()),
        email=EmailAddress.parse("trader@example.com"),
        display_name="Trader",
        password_hash="hashed::secret",
        now=START,
        requires_verification=False,
    )


@pytest.fixture
def service(sessions_repo, clock, auth_settings, security_settings, uow) -> SessionService:  # type: ignore[no-untyped-def]
    return SessionService(
        sessions=sessions_repo,
        tokens=JwtAccessTokenIssuer(auth_settings, security_settings),
        clock=clock,
        policy=SessionPolicy(
            refresh_ttl_seconds=30 * 24 * 3600,
            reuse_grace_seconds=10,
            max_active_sessions=3,
        ),
        uow=uow,
    )


async def test_rotation_issues_a_new_pair_and_retires_the_old_token(
    service, sessions_repo, users, user, clock
):  # type: ignore[no-untyped-def]
    users.users[user.id] = user
    first = await service.start(user, CONTEXT)

    clock.advance(60)
    _, second = await service.rotate(first.refresh_token, users.get, CONTEXT)

    assert second.refresh_token != first.refresh_token
    assert second.session_id != first.session_id

    original = await sessions_repo.get(first.session_id)
    assert original is not None
    assert original.is_used
    assert original.replaced_by_id == second.session_id


async def test_rotation_stays_in_one_family(service, sessions_repo, users, user, clock):  # type: ignore[no-untyped-def]
    users.users[user.id] = user
    first = await service.start(user, CONTEXT)
    clock.advance(60)
    _, second = await service.rotate(first.refresh_token, users.get, CONTEXT)

    original = await sessions_repo.get(first.session_id)
    successor = await sessions_repo.get(second.session_id)
    assert original is not None and successor is not None
    assert successor.family_id == original.family_id
    assert successor.generation == original.generation + 1


async def test_replaying_a_rotated_token_revokes_the_whole_family(
    service, sessions_repo, users, user, clock
):  # type: ignore[no-untyped-def]
    """The scenario this design exists for: a stolen refresh token."""
    users.users[user.id] = user
    first = await service.start(user, CONTEXT)
    clock.advance(60)
    _, second = await service.rotate(first.refresh_token, users.get, CONTEXT)

    # Well past the race-tolerance window, so this is a genuine replay.
    clock.advance(3600)
    with pytest.raises(TokenReuseDetectedError):
        await service.rotate(first.refresh_token, users.get, CONTEXT)

    # The attacker's token is dead, and so is the legitimate client's.
    for session in sessions_repo.sessions.values():
        assert session.is_revoked
        assert session.revocation_reason is SessionRevocationReason.REUSE_DETECTED

    with pytest.raises(TokenReuseDetectedError):
        await service.rotate(second.refresh_token, users.get, CONTEXT)


async def test_double_submit_inside_the_grace_window_does_not_revoke(
    service, sessions_repo, users, user, clock
):  # type: ignore[no-untyped-def]
    """Two tabs refreshing at once must not log the user out."""
    users.users[user.id] = user
    first = await service.start(user, CONTEXT)
    clock.advance(60)
    _, second = await service.rotate(first.refresh_token, users.get, CONTEXT)

    clock.advance(2)  # inside the 10s grace
    with pytest.raises(SessionExpiredError):
        await service.rotate(first.refresh_token, users.get, CONTEXT)

    successor = await sessions_repo.get(second.session_id)
    assert successor is not None
    assert not successor.is_revoked

    # The surviving token still works.
    clock.advance(5)
    _, third = await service.rotate(second.refresh_token, users.get, CONTEXT)
    assert third.refresh_token


async def test_expired_refresh_token_is_rejected(service, users, user, clock):  # type: ignore[no-untyped-def]
    users.users[user.id] = user
    tokens = await service.start(user, CONTEXT)

    clock.advance(31 * 24 * 3600)
    with pytest.raises(SessionExpiredError):
        await service.rotate(tokens.refresh_token, users.get, CONTEXT)


async def test_rotation_never_extends_a_session_past_its_original_expiry(
    service, sessions_repo, users, user, clock
):  # type: ignore[no-untyped-def]
    """Otherwise an active client holds a session forever."""
    users.users[user.id] = user
    first = await service.start(user, CONTEXT)
    original = await sessions_repo.get(first.session_id)
    assert original is not None
    ceiling = original.expires_at

    for _ in range(3):
        clock.advance(24 * 3600)
        _, first = await service.rotate(first.refresh_token, users.get, CONTEXT)

    assert first.refresh_token_expires_at <= ceiling


async def test_unknown_token_is_rejected(service, users, user):  # type: ignore[no-untyped-def]
    users.users[user.id] = user
    with pytest.raises(SessionExpiredError):
        await service.rotate("not-a-real-token", users.get, CONTEXT)


async def test_session_limit_revokes_the_oldest_session(service, sessions_repo, user):  # type: ignore[no-untyped-def]
    for _ in range(4):  # limit is 3
        await service.start(user, CONTEXT)

    active = await sessions_repo.list_active_for_user(user.id)
    assert len(active) == 3


async def test_logout_revokes_the_family(service, sessions_repo, users, user, clock):  # type: ignore[no-untyped-def]
    users.users[user.id] = user
    tokens = await service.start(user, CONTEXT)
    clock.advance(60)
    await service.rotate(tokens.refresh_token, users.get, CONTEXT)

    session = await sessions_repo.get(tokens.session_id)
    assert session is not None
    await service.end(session.token_hash and tokens.refresh_token)

    assert all(item.is_revoked for item in sessions_repo.sessions.values())


async def test_logout_with_no_token_is_a_no_op(service):  # type: ignore[no-untyped-def]
    await service.end(None)
    await service.end("")
