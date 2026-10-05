"""Registration and password login."""

from __future__ import annotations

import pytest

from chartnexus.contexts.identity.application.authenticate import (
    LoginCommand,
    LoginWithPassword,
    RegisterUser,
    RegisterUserCommand,
    RegistrationPolicy,
)
from chartnexus.contexts.identity.application.session_service import (
    SessionPolicy,
    SessionService,
)
from chartnexus.contexts.identity.domain.errors import (
    AccountSuspendedError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    PasswordLoginUnavailableError,
    PhoneAlreadyRegisteredError,
    RegistrationDisabledError,
)
from chartnexus.contexts.identity.domain.password_policy import PasswordPolicy
from chartnexus.contexts.identity.domain.user import User
from chartnexus.contexts.identity.domain.value_objects import (
    EmailAddress,
    PhoneNumber,
    UserStatus,
)
from chartnexus.infrastructure.security.token_signer import JwtAccessTokenIssuer
from chartnexus.shared_kernel.domain.errors import RateLimitError, ValidationError
from chartnexus.shared_kernel.types.identifiers import TenantId, new_id
from tests.unit.contexts.identity.conftest import START

pytestmark = pytest.mark.unit

EMAIL = "trader@example.com"
PHONE = "9876543210"
PHONE_E164 = "+919876543210"
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
        phone=PhoneNumber.parse(PHONE),
    )
    user.status = status
    return user


# --- registration ----------------------------------------------------------


async def test_registration_creates_an_active_signed_in_user(register, uow):  # type: ignore[no-untyped-def]
    result = await register(RegisterUserCommand(email=EMAIL, password=PASSWORD, phone=PHONE))

    assert result.is_new_user
    assert result.user.email == EMAIL
    assert result.user.roles == ("owner",)
    assert result.tokens.access_token
    assert uow.commits == 1


async def test_registration_normalises_the_email_address(register, users):  # type: ignore[no-untyped-def]
    await register(
        RegisterUserCommand(email="  Trader@Example.COM ", password=PASSWORD, phone=PHONE)
    )
    assert await users.find_by_email(EmailAddress("trader@example.com")) is not None


async def test_registration_normalises_the_phone_number(register, users):  # type: ignore[no-untyped-def]
    await register(RegisterUserCommand(email=EMAIL, password=PASSWORD, phone="+91 98765 43210"))
    assert await users.find_by_phone(PhoneNumber(PHONE_E164)) is not None


async def test_duplicate_registration_is_rejected(register):  # type: ignore[no-untyped-def]
    await register(RegisterUserCommand(email=EMAIL, password=PASSWORD, phone=PHONE))
    with pytest.raises(EmailAlreadyRegisteredError):
        # A different phone, so the email is unambiguously what collides.
        await register(
            RegisterUserCommand(email=EMAIL.upper(), password=PASSWORD, phone="9812345678")
        )


async def test_duplicate_phone_is_rejected(register):  # type: ignore[no-untyped-def]
    await register(RegisterUserCommand(email=EMAIL, password=PASSWORD, phone=PHONE))
    with pytest.raises(PhoneAlreadyRegisteredError):
        # A different email, and the number spelled differently, so this proves
        # the clash is caught after normalisation rather than by string equality.
        await register(
            RegisterUserCommand(
                email="someone-else@example.com", password=PASSWORD, phone="+91-98765-43210"
            )
        )


async def test_weak_password_is_rejected_before_any_write(register, users):  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        await register(RegisterUserCommand(email=EMAIL, password="short", phone=PHONE))
    assert not users.users


async def test_invalid_phone_is_rejected_before_any_write(register, users):  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        # Indian mobile numbers never start with 1.
        await register(RegisterUserCommand(email=EMAIL, password=PASSWORD, phone="1234567890"))
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
        await closed(RegisterUserCommand(email=EMAIL, password=PASSWORD, phone=PHONE))


# --- login -----------------------------------------------------------------


async def test_login_succeeds_and_records_the_time(login, users, hasher, clock):  # type: ignore[no-untyped-def]
    user = _existing_user(hasher)
    users.users[user.id] = user

    result = await login(LoginCommand(identifier=EMAIL, password=PASSWORD))

    assert result.user.email == EMAIL
    assert not result.is_new_user
    assert users.users[user.id].last_login_at == clock.now()


async def test_wrong_password_is_rejected_and_counted(login, users, hasher, rate_limiter):  # type: ignore[no-untyped-def]
    user = _existing_user(hasher)
    users.users[user.id] = user

    with pytest.raises(InvalidCredentialsError):
        await login(LoginCommand(identifier=EMAIL, password="not-the-password"))

    assert users.users[user.id].failed_login_count == 1
    assert rate_limiter.failures[f"login:{EMAIL}"] == 1


async def test_login_succeeds_with_a_phone_number(login, users, hasher, clock):  # type: ignore[no-untyped-def]
    user = _existing_user(hasher)
    users.users[user.id] = user

    result = await login(LoginCommand(identifier=PHONE, password=PASSWORD))

    assert result.user.email == EMAIL
    assert result.user.phone == PHONE_E164
    assert users.users[user.id].last_login_at == clock.now()


async def test_login_by_phone_accepts_any_spelling_of_the_number(login, users, hasher):  # type: ignore[no-untyped-def]
    """The stored number is E.164; what someone types rarely is."""
    user = _existing_user(hasher)
    users.users[user.id] = user

    for typed in (PHONE, PHONE_E164, "+91 98765 43210", "09876543210"):
        result = await login(LoginCommand(identifier=typed, password=PASSWORD))
        assert result.user.email == EMAIL


async def test_unknown_account_still_burns_a_hash_verification(login, hasher):  # type: ignore[no-untyped-def]
    """Otherwise response time reveals which addresses are registered."""
    with pytest.raises(InvalidCredentialsError):
        await login(LoginCommand(identifier="nobody@example.com", password=PASSWORD))

    assert hasher.dummy_verifications == 1


async def test_unknown_phone_still_burns_a_hash_verification(login, hasher):  # type: ignore[no-untyped-def]
    with pytest.raises(InvalidCredentialsError):
        await login(LoginCommand(identifier="9812345678", password=PASSWORD))

    assert hasher.dummy_verifications == 1


async def test_malformed_identifier_looks_like_wrong_credentials(login, hasher):  # type: ignore[no-untyped-def]
    """A validation error here would confirm the identifier does not exist.

    It must be indistinguishable from a wrong password — same error, and a
    hash burned so the timing matches too.
    """
    with pytest.raises(InvalidCredentialsError):
        await login(LoginCommand(identifier="not-an-identifier", password=PASSWORD))

    assert hasher.dummy_verifications == 1


async def test_unknown_and_wrong_password_raise_the_same_error(login, users, hasher):  # type: ignore[no-untyped-def]
    user = _existing_user(hasher)
    users.users[user.id] = user

    with pytest.raises(InvalidCredentialsError) as unknown:
        await login(LoginCommand(identifier="nobody@example.com", password=PASSWORD))
    with pytest.raises(InvalidCredentialsError) as wrong:
        await login(LoginCommand(identifier=EMAIL, password="wrong"))

    assert str(unknown.value) == str(wrong.value)
    assert unknown.value.code == wrong.value.code


async def test_suspended_account_cannot_sign_in(login, users, hasher):  # type: ignore[no-untyped-def]
    user = _existing_user(hasher, status=UserStatus.SUSPENDED)
    users.users[user.id] = user

    with pytest.raises(AccountSuspendedError):
        await login(LoginCommand(identifier=EMAIL, password=PASSWORD))


async def test_account_status_is_only_revealed_after_the_password_is_proven(login, users, hasher):  # type: ignore[no-untyped-def]
    """A wrong password on a suspended account must look like any other failure."""
    user = _existing_user(hasher, status=UserStatus.SUSPENDED)
    users.users[user.id] = user

    with pytest.raises(InvalidCredentialsError):
        await login(LoginCommand(identifier=EMAIL, password="wrong-password"))


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
        await login(LoginCommand(identifier=EMAIL, password=PASSWORD))

    assert error.value.code == "use_sso"


async def test_rate_limiter_blocks_after_too_many_failures(login, users, hasher, rate_limiter):  # type: ignore[no-untyped-def]
    rate_limiter.limit = 3
    user = _existing_user(hasher)
    users.users[user.id] = user

    for _ in range(3):
        with pytest.raises(InvalidCredentialsError):
            await login(LoginCommand(identifier=EMAIL, password="wrong"))

    # Even the correct password is now refused until the lockout expires.
    with pytest.raises(RateLimitError):
        await login(LoginCommand(identifier=EMAIL, password=PASSWORD))


async def test_successful_login_clears_the_failure_counter(login, users, hasher, rate_limiter):  # type: ignore[no-untyped-def]
    user = _existing_user(hasher)
    users.users[user.id] = user

    with pytest.raises(InvalidCredentialsError):
        await login(LoginCommand(identifier=EMAIL, password="wrong"))
    await login(LoginCommand(identifier=EMAIL, password=PASSWORD))

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

    await login(LoginCommand(identifier=EMAIL, password=PASSWORD))

    assert users.users[user.id].password_hash == f"hashed::{PASSWORD}"
