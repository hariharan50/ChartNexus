"""Password registration and login."""

from __future__ import annotations

from dataclasses import dataclass, field

from marketcompass.contexts.identity.application.dto import (
    AuthenticationResult,
    RequestContextInput,
    UserView,
)
from marketcompass.contexts.identity.application.ports import (
    Clock,
    LoginRateLimiter,
    PasswordHasher,
    UnitOfWork,
    UserRepository,
)
from marketcompass.contexts.identity.application.session_service import SessionService
from marketcompass.contexts.identity.domain.errors import (
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    PasswordLoginUnavailableError,
    PhoneAlreadyRegisteredError,
    RegistrationDisabledError,
)
from marketcompass.contexts.identity.domain.password_policy import PasswordPolicy
from marketcompass.contexts.identity.domain.user import User
from marketcompass.contexts.identity.domain.value_objects import (
    AuthProvider,
    EmailAddress,
    PhoneNumber,
    RawPassword,
)
from marketcompass.shared_kernel.domain.errors import ValidationError
from marketcompass.shared_kernel.types.identifiers import TenantId, new_id


@dataclass(frozen=True, slots=True)
class RegisterUserCommand:
    email: str
    password: str
    phone: str
    display_name: str = ""
    context: RequestContextInput = field(default_factory=RequestContextInput)


@dataclass(frozen=True, slots=True)
class LoginCommand:
    """``identifier`` is an email address or a phone number — see
    :func:`_parse_identifier` for how the two are told apart."""

    identifier: str
    password: str
    context: RequestContextInput = field(default_factory=RequestContextInput)


def _parse_identifier(raw: str) -> EmailAddress | PhoneNumber:
    """Decide whether the sign-in identifier is an email or a phone number.

    An ``@`` is the discriminator: no Indian mobile number contains one, and no
    email address is valid without one. Raises :class:`ValidationError` when
    neither form parses — the caller turns that into invalid credentials rather
    than surfacing it, so a malformed identifier reveals nothing.
    """
    return EmailAddress.parse(raw) if "@" in raw else PhoneNumber.parse(raw)


@dataclass(frozen=True, slots=True)
class RegistrationPolicy:
    enabled: bool
    require_email_verification: bool


class RegisterUser:
    """Create an account and, unless verification is required, sign it in."""

    def __init__(
        self,
        *,
        users: UserRepository,
        hasher: PasswordHasher,
        sessions: SessionService,
        clock: Clock,
        uow: UnitOfWork,
        password_policy: PasswordPolicy,
        registration_policy: RegistrationPolicy,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._sessions = sessions
        self._clock = clock
        self._uow = uow
        self._password_policy = password_policy
        self._registration_policy = registration_policy

    async def __call__(self, command: RegisterUserCommand) -> AuthenticationResult:
        if not self._registration_policy.enabled:
            raise RegistrationDisabledError

        email = EmailAddress.parse(command.email)
        phone = PhoneNumber.parse(command.phone)
        password = RawPassword(command.password)
        self._password_policy.validate(password, email=email, phone=phone)

        if await self._users.email_exists(email):
            # Registration cannot hide that an address is taken — the account
            # would collide. The mitigation is rate limiting, not vagueness.
            raise EmailAlreadyRegisteredError

        if await self._users.phone_exists(phone):
            # Same reasoning as the email check: a phone number identifies an
            # account at sign-in, so it has to be unique and the clash has to
            # be reported.
            raise PhoneAlreadyRegisteredError

        now = self._clock.now()
        user = User.register_with_password(
            # Every account starts as the owner of its own tenant. The tenancy
            # context takes over organisation membership from here.
            tenant_id=TenantId(new_id()),
            email=email,
            display_name=command.display_name,
            password_hash=self._hasher.hash(password.value),
            now=now,
            requires_verification=self._registration_policy.require_email_verification,
            phone=phone,
        )
        await self._users.add(user)

        if self._registration_policy.require_email_verification:
            # The account exists but cannot hold a session yet. The verification
            # email is sent by a subscriber to the registration event.
            await self._uow.commit()
            raise EmailNotVerifiedError

        tokens = await self._sessions.start(user, command.context)
        await self._uow.commit()
        return AuthenticationResult(user=UserView.of(user), tokens=tokens, is_new_user=True)


class LoginWithPassword:
    def __init__(
        self,
        *,
        users: UserRepository,
        hasher: PasswordHasher,
        sessions: SessionService,
        clock: Clock,
        uow: UnitOfWork,
        rate_limiter: LoginRateLimiter,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._sessions = sessions
        self._clock = clock
        self._uow = uow
        self._rate_limiter = rate_limiter

    async def __call__(self, command: LoginCommand) -> AuthenticationResult:
        try:
            credential = _parse_identifier(command.identifier)
        except ValidationError:
            # An identifier that is neither a valid email nor a valid phone
            # cannot match an account. Answering "invalid credentials" rather
            # than "malformed input" keeps the response — and its timing —
            # indistinguishable from a wrong password.
            self._hasher.dummy_verify()
            raise InvalidCredentialsError from None

        # Both identifiers normalise into their own namespace, so an account
        # reachable two ways carries two lockout budgets. Accepted for now:
        # each key still throttles, and tightening it means keying on user id,
        # which is not known until after the lookup this key guards.
        rate_key = f"login:{credential.value}"
        await self._rate_limiter.check(rate_key)

        user = (
            await self._users.find_by_email(credential)
            if isinstance(credential, EmailAddress)
            else await self._users.find_by_phone(credential)
        )

        if user is None:
            # Hash anyway. Returning early here makes "unknown address" measurably
            # faster than "wrong password", which is an enumeration oracle.
            self._hasher.dummy_verify()
            await self._rate_limiter.record_failure(rate_key)
            raise InvalidCredentialsError

        if not user.has_password:
            self._hasher.dummy_verify()
            provider = next(
                (
                    identity.provider.value
                    for identity in user.federated_identities
                    if identity.provider is not AuthProvider.PASSWORD
                ),
                AuthProvider.GOOGLE.value,
            )
            raise PasswordLoginUnavailableError(provider)

        assert user.password_hash is not None  # noqa: S101 — guarded by has_password
        if not self._hasher.verify(command.password, user.password_hash):
            now = self._clock.now()
            user.record_failed_login(now)
            await self._users.update(user)
            await self._uow.commit()
            await self._rate_limiter.record_failure(rate_key)
            raise InvalidCredentialsError

        # Status is checked only after the password is proven, so a suspended
        # account cannot be discovered without its credentials.
        user.ensure_can_authenticate()

        now = self._clock.now()
        if self._hasher.needs_rehash(user.password_hash):
            # The cost parameters were raised since this hash was written; the
            # only moment we hold the plaintext is right now.
            user.change_password(self._hasher.hash(command.password), now)

        user.record_successful_login(now)
        await self._users.update(user)

        tokens = await self._sessions.start(user, command.context)
        await self._uow.commit()
        await self._rate_limiter.reset(rate_key)

        return AuthenticationResult(user=UserView.of(user), tokens=tokens)
