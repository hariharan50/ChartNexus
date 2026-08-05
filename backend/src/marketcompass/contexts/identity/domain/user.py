"""The User aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from marketcompass.contexts.identity.domain.errors import (
    AccountDisabledError,
    AccountSuspendedError,
    EmailNotVerifiedError,
    IdentityConflictError,
)
from marketcompass.contexts.identity.domain.value_objects import (
    AuthProvider,
    EmailAddress,
    PhoneNumber,
    Role,
    UserStatus,
)
from marketcompass.shared_kernel.domain.errors import ValidationError
from marketcompass.shared_kernel.types.identifiers import TenantId, UserId, new_id


@dataclass(slots=True)
class FederatedIdentity:
    """A link to an external identity provider account.

    ``subject`` is the provider's stable user id — for Google the ``sub`` claim,
    which never changes, unlike the email address.
    """

    provider: AuthProvider
    subject: str
    email: EmailAddress
    linked_at: datetime

    def __post_init__(self) -> None:
        if not self.subject:
            raise ValidationError("federated identity requires a subject")


@dataclass(slots=True)
class User:
    """A person who can sign in.

    Password material lives here only as a hash. The aggregate never sees a raw
    password: hashing happens in an adapter behind the ``PasswordHasher`` port,
    because the algorithm is an infrastructure concern.
    """

    id: UserId
    tenant_id: TenantId
    email: EmailAddress
    display_name: str
    status: UserStatus
    roles: frozenset[Role]
    password_hash: str | None
    # Optional on the aggregate even though signup now demands one: accounts
    # created before this field existed, and Google sign-ups, legitimately have
    # none. Only sign-in-by-phone depends on it being set.
    phone: PhoneNumber | None = None
    email_verified_at: datetime | None = None
    # Reserved for the SMS/OTP flow. Nothing sets it yet; having the field means
    # adding verification later does not need another migration of this shape.
    phone_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    failed_login_count: int = 0
    federated_identities: list[FederatedIdentity] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # -- construction -------------------------------------------------------

    @classmethod
    def register_with_password(
        cls,
        *,
        tenant_id: TenantId,
        email: EmailAddress,
        display_name: str,
        password_hash: str,
        now: datetime,
        requires_verification: bool,
        phone: PhoneNumber | None = None,
        roles: frozenset[Role] = frozenset({Role.OWNER}),
    ) -> User:
        return cls(
            id=UserId(new_id()),
            tenant_id=tenant_id,
            email=email,
            display_name=_clean_display_name(display_name, email),
            status=(
                UserStatus.PENDING_VERIFICATION if requires_verification else UserStatus.ACTIVE
            ),
            roles=roles,
            password_hash=password_hash,
            phone=phone,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def register_with_google(
        cls,
        *,
        tenant_id: TenantId,
        email: EmailAddress,
        display_name: str,
        subject: str,
        now: datetime,
        roles: frozenset[Role] = frozenset({Role.OWNER}),
    ) -> User:
        """Create an account from a Google sign-in.

        Google has already proven control of the address, so the account starts
        active and verified — and with no password, which is what makes
        :meth:`has_password` meaningful later.
        """
        return cls(
            id=UserId(new_id()),
            tenant_id=tenant_id,
            email=email,
            display_name=_clean_display_name(display_name, email),
            status=UserStatus.ACTIVE,
            roles=roles,
            password_hash=None,
            email_verified_at=now,
            federated_identities=[
                FederatedIdentity(
                    provider=AuthProvider.GOOGLE,
                    subject=subject,
                    email=email,
                    linked_at=now,
                )
            ],
            created_at=now,
            updated_at=now,
        )

    # -- queries ------------------------------------------------------------

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    def identity_for(self, provider: AuthProvider) -> FederatedIdentity | None:
        return next(
            (identity for identity in self.federated_identities if identity.provider is provider),
            None,
        )

    def has_role(self, role: Role) -> bool:
        return role in self.roles

    # -- behaviour ----------------------------------------------------------

    def ensure_can_authenticate(self) -> None:
        """Raise if this account is not allowed to start a session."""
        if self.status is UserStatus.SUSPENDED:
            raise AccountSuspendedError
        if self.status is UserStatus.DEACTIVATED:
            raise AccountDisabledError
        if self.status is UserStatus.PENDING_VERIFICATION:
            raise EmailNotVerifiedError

    def link_google_identity(self, *, subject: str, email: EmailAddress, now: datetime) -> None:
        """Attach a Google account to an existing user.

        Refuses to re-point an existing link at a different Google account: that
        would let whoever controls the new account inherit this user's data.
        """
        existing = self.identity_for(AuthProvider.GOOGLE)
        if existing is not None:
            if existing.subject != subject:
                raise IdentityConflictError(
                    "A different Google account is already linked to this user."
                )
            return

        self.federated_identities.append(
            FederatedIdentity(
                provider=AuthProvider.GOOGLE,
                subject=subject,
                email=email,
                linked_at=now,
            )
        )
        self.updated_at = now

    def mark_email_verified(self, now: datetime) -> None:
        if self.is_email_verified:
            return
        self.email_verified_at = now
        if self.status is UserStatus.PENDING_VERIFICATION:
            self.status = UserStatus.ACTIVE
        self.updated_at = now

    def record_successful_login(self, now: datetime) -> None:
        self.last_login_at = now
        self.failed_login_count = 0
        self.updated_at = now

    def record_failed_login(self, now: datetime) -> None:
        self.failed_login_count += 1
        self.updated_at = now

    def change_password(self, password_hash: str, now: datetime) -> None:
        self.password_hash = password_hash
        self.updated_at = now

    def rename(self, display_name: str, now: datetime) -> None:
        self.display_name = _clean_display_name(display_name, self.email)
        self.updated_at = now


def _clean_display_name(display_name: str, email: EmailAddress) -> str:
    cleaned = " ".join((display_name or "").split())[:120]
    return cleaned or email.value.split("@", 1)[0]
