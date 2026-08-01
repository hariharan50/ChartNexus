"""Registration and password login."""

from __future__ import annotations

import pytest

from marketcompass.contexts.identity.application.authenticate import (
    LoginCommand,
    LoginWithPassword,
    RegisterUser,
    RegisterUserCommand,
    RegistrationPolicy,
)
from marketcompass.contexts.identity.application.session_service import (
    SessionPolicy,
    SessionService,
)
from marketcompass.contexts.identity.domain.errors import (
    AccountSuspendedError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    PasswordLoginUnavailableError,
    RegistrationDisabledError,
)
from marketcompass.contexts.identity.domain.password_policy import PasswordPolicy
from marketcompass.contexts.identity.domain.user import User
from marketcompass.contexts.identity.domain.value_objects import EmailAddress, UserStatus
from marketcompass.infrastructure.security.token_signer import JwtAccessTokenIssuer
from marketcompass.shared_kernel.domain.errors import RateLimitError, ValidationError
from marketcompass.shared_kernel.types.identifiers import TenantId, new_id
from tests.unit.contexts.identity.conftest import START

pytestmark = pytest.mark.unit

EMAIL = "trader@example.com"
PASSWORD = "a-perfectly-fine-password"


@pytest.fixture
def session_service(sessions_repo, clock, auth_settings, security_settings, uow):  # type: ignore[no-untyped-def]
    return SessionService(
        sessions=sessions_repo,
        tokens=JwtAccessTokenIssuer(auth_settings, security_settings),
        clock=clock,
        policy=SessionPolicy(
            refresh_ttl_seconds=3600, reuse_grace_seconds=10, max_active_sessions=5
        ),
        uow=uow,
    )


@pytest.fixture
def register(users, hasher, session_service, clock, uow):  # type: ignore[no-untyped-def]
    return RegisterUser(
        users=users,
        hasher=hasher,
        sessions=session_service,
        clock=clock,
        uow=uow,
        password_policy=PasswordPolicy(min_length=12),
        registration_policy=RegistrationPolicy(enabled=True, require_email_verification=False),
    )


@pytest.fixture
def login(users, hasher, session_service, clock, uow, rate_limiter):  # type: ignore[no-untyped-def]
    return LoginWithPassword(
        users=users,
        hasher=hasher,
        sessions=session_service,
        clock=clock,
        uow=uow,
        rate_limiter=rate_limiter,
    )


def _existing_user(hasher, *, status=UserStatus.ACTIVE, password=PASSWORD) -> User:  # type: ignore[no-untyped-def]
    user = User.register_with_password(
        tenant_id=TenantId(new_id()),
        email=EmailAddress.parse(EMAIL),
        display_name="Trader",
        password_hash=hasher.hash(password),
        now=START,
        requires_verification=False,
    )
    user.status = status
    return user


# --- registration ----------------------------------------------------------


async def test_registration_creates_an_active_signed_in_user(register, uow):  # type: ignore[no-untyped-def]
    result = await register(RegisterUserCommand(email=EMAIL, password=PASSWORD))

    assert result.is_new_user
    assert result.user.email == EMAIL
    assert result.user.roles == ("owner",)
    assert result.tokens.access_token
    assert uow.commits == 1


async def test_registration_normalises_the_email_address(register, users):  # type: ignore[no-untyped-def]
    await register(RegisterUserCommand(email="  Trader@Example.COM ", password=PASSWORD))
    assert await users.find_by_email(EmailAddress("trader@example.com")) is not None


async def test_duplicate_registration_is_rejected(register):  # type: ignore[no-untyped-def]
    await register(RegisterUserCommand(email=EMAIL, password=PASSWORD))
    with pytest.raises(EmailAlreadyRegisteredError):
        await register(RegisterUserCommand(email=EMAIL.upper(), password=PASSWORD))


async def test_weak_password_is_rejected_before_any_write(register, users):  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        await register(RegisterUserCommand(email=EMAIL, password="short"))
    assert not users.users


async def test_registration_can_be_closed(users, hasher, session_service, clock, uow):  # type: ignore[no-untyped-def]
    closed = RegisterUser(
        users=users,
        hasher=hasher,
        sessions=session_service,
        clock=clock,
        uow=uow,
        password_policy=PasswordPolicy(),
        registration_policy=RegistrationPolicy(enabled=False, require_email_verification=False),
    )
    with pytest.raises(RegistrationDisabledError):
        await closed(RegisterUserCommand(email=EMAIL, password=PASSWORD))


# --- login -----------------------------------------------------------------


async def test_login_succeeds_and_records_the_time(login, users, hasher, clock):  # type: ignore[no-untyped-def]
    user = _existing_user(hasher)
    users.users[user.id] = user

    result = await login(LoginCommand(email=EMAIL, password=PASSWORD))

    assert result.user.email == EMAIL
    assert not result.is_new_user
    assert users.users[user.id].last_login_at == clock.now()


async def test_wrong_password_is_rejected_and_counted(login, users, hasher, rate_limiter):  # type: ignore[no-untyped-def]
    user = _existing_user(hasher)
    users.users[user.id] = user

    with pytest.raises(InvalidCredentialsError):
        await login(LoginCommand(email=EMAIL, password="not-the-password"))

    assert users.users[user.id].failed_login_count == 1
    assert rate_limiter.failures[f"login:{EMAIL}"] == 1


async def test_unknown_account_still_burns_a_hash_verification(login, hasher):  # type: ignore[no-untyped-def]
    """Otherwise response time reveals which addresses are registered."""
    with pytest.raises(InvalidCredentialsError):
        await login(LoginCommand(email="nobody@example.com", password=PASSWORD))

    assert hasher.dummy_verifications == 1


async def test_unknown_and_wrong_password_raise_the_same_error(login, users, hasher):  # type: ignore[no-untyped-def]
    user = _existing_user(hasher)
    users.users[user.id] = user

    with pytest.raises(InvalidCredentialsError) as unknown:
        await login(LoginCommand(email="nobody@example.com", password=PASSWORD))
    with pytest.raises(InvalidCredentialsError) as wrong:
        await login(LoginCommand(email=EMAIL, password="wrong"))

    assert str(unknown.value) == str(wrong.value)
    assert unknown.value.code == wrong.value.code


async def test_suspended_account_cannot_sign_in(login, users, hasher):  # type: ignore[no-untyped-def]
    user = _existing_user(hasher, status=UserStatus.SUSPENDED)
    users.users[user.id] = user

    with pytest.raises(AccountSuspendedError):
        await login(LoginCommand(email=EMAIL, password=PASSWORD))


async def test_account_status_is_only_revealed_after_the_password_is_proven(login, users, hasher):  # type: ignore[no-untyped-def]
    """A wrong password on a suspended account must look like any other failure."""
    user = _existing_user(hasher, status=UserStatus.SUSPENDED)
    users.users[user.id] = user

    with pytest.raises(InvalidCredentialsError):
        await login(LoginCommand(email=EMAIL, password="wrong-password"))


async def test_sso_only_account_is_told_to_use_google(login, users):  # type: ignore[no-untyped-def]
    user = User.register_with_google(
        tenant_id=TenantId(new_id()),
        email=EmailAddress.parse(EMAIL),
        display_name="Trader",
        subject="google-1",
        now=START,
    )
    users.users[user.id] = user

    with pytest.raises(PasswordLoginUnavailableError) as error:
        await login(LoginCommand(email=EMAIL, password=PASSWORD))

    assert error.value.code == "use_sso"


async def test_rate_limiter_blocks_after_too_many_failures(login, users, hasher, rate_limiter):  # type: ignore[no-untyped-def]
    rate_limiter.limit = 3
    user = _existing_user(hasher)
    users.users[user.id] = user

    for _ in range(3):
        with pytest.raises(InvalidCredentialsError):
            await login(LoginCommand(email=EMAIL, password="wrong"))

    # Even the correct password is now refused until the lockout expires.
    with pytest.raises(RateLimitError):
        await login(LoginCommand(email=EMAIL, password=PASSWORD))


async def test_successful_login_clears_the_failure_counter(login, users, hasher, rate_limiter):  # type: ignore[no-untyped-def]
    user = _existing_user(hasher)
    users.users[user.id] = user

    with pytest.raises(InvalidCredentialsError):
        await login(LoginCommand(email=EMAIL, password="wrong"))
    await login(LoginCommand(email=EMAIL, password=PASSWORD))

    assert f"login:{EMAIL}" not in rate_limiter.failures
    assert users.users[user.id].failed_login_count == 0


async def test_legacy_hash_is_upgraded_on_successful_login(login, users, hasher):  # type: ignore[no-untyped-def]
    user = _existing_user(hasher)
    user.password_hash = f"legacy::{PASSWORD}"
    users.users[user.id] = user

    # FakeHasher.verify only accepts the modern prefix, so make the legacy hash
    # verify while still reporting that it needs rehashing.
    original_verify = hasher.verify
    hasher.verify = lambda password, password_hash: (  # type: ignore[method-assign]
        original_verify(password, password_hash) or password_hash == f"legacy::{password}"
    )

    await login(LoginCommand(email=EMAIL, password=PASSWORD))

    assert users.users[user.id].password_hash == f"hashed::{PASSWORD}"
