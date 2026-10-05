"""User repository.

Maps between the ``User`` aggregate and its rows. The aggregate has no ORM
inheritance and no SQLAlchemy imports — translation happens here, which is what
keeps the domain testable without a database.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from chartnexus.contexts.identity.domain.errors import (
    EmailAlreadyRegisteredError,
    PhoneAlreadyRegisteredError,
)
from chartnexus.contexts.identity.domain.user import FederatedIdentity, User
from chartnexus.contexts.identity.domain.value_objects import (
    AuthProvider,
    EmailAddress,
    PhoneNumber,
    Role,
    UserStatus,
)
from chartnexus.infrastructure.persistence.postgresql.models.identity.user import (
    FederatedIdentityRecord,
    UserRecord,
)
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId


class SqlAlchemyUserRepository:
    """Implements the ``UserRepository`` port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UserId) -> User | None:
        record = await self._session.get(UserRecord, user_id)
        return _to_domain(record) if record else None

    async def find_by_email(self, email: EmailAddress) -> User | None:
        result = await self._session.execute(
            select(UserRecord).where(UserRecord.email == email.value)
        )
        record = result.scalar_one_or_none()
        return _to_domain(record) if record else None

    async def find_by_phone(self, phone: PhoneNumber) -> User | None:
        result = await self._session.execute(
            select(UserRecord).where(UserRecord.phone == phone.value)
        )
        record = result.scalar_one_or_none()
        return _to_domain(record) if record else None

    async def find_by_google_subject(self, subject: str) -> User | None:
        result = await self._session.execute(
            select(UserRecord)
            .join(FederatedIdentityRecord)
            .where(
                FederatedIdentityRecord.provider == AuthProvider.GOOGLE.value,
                FederatedIdentityRecord.subject == subject,
            )
        )
        record = result.scalar_one_or_none()
        return _to_domain(record) if record else None

    async def email_exists(self, email: EmailAddress) -> bool:
        result = await self._session.execute(
            select(exists().where(func.lower(UserRecord.email) == email.value))
        )
        return bool(result.scalar())

    async def phone_exists(self, phone: PhoneNumber) -> bool:
        result = await self._session.execute(
            select(exists().where(UserRecord.phone == phone.value))
        )
        return bool(result.scalar())

    async def add(self, user: User) -> None:
        record = UserRecord(
            id=user.id,
            tenant_id=user.tenant_id,
            email=user.email.value,
            phone=user.phone.value if user.phone else None,
            display_name=user.display_name,
            status=user.status.value,
            password_hash=user.password_hash,
            roles=sorted(role.value for role in user.roles),
            email_verified_at=user.email_verified_at,
            phone_verified_at=user.phone_verified_at,
            last_login_at=user.last_login_at,
            failed_login_count=user.failed_login_count,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        record.identities = [
            FederatedIdentityRecord(
                user_id=user.id,
                provider=identity.provider.value,
                subject=identity.subject,
                email=identity.email.value,
                created_at=identity.linked_at,
                updated_at=identity.linked_at,
            )
            for identity in user.federated_identities
        ]
        self._session.add(record)
        # Surfaces a unique-violation here, inside the use case, rather than at
        # commit time when the handler can no longer translate it. The use case
        # pre-checks both columns, but two concurrent registrations can still
        # both pass that check and race to INSERT — without this the loser gets
        # a 500 instead of the same 409 the pre-check would have produced.
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise _translate_unique_violation(exc) from exc

    async def update(self, user: User) -> None:
        record = await self._session.get(UserRecord, user.id)
        if record is None:
            msg = f"user {user.id} disappeared between load and save"
            raise LookupError(msg)

        record.email = user.email.value
        record.phone = user.phone.value if user.phone else None
        record.display_name = user.display_name
        record.status = user.status.value
        record.password_hash = user.password_hash
        record.roles = sorted(role.value for role in user.roles)
        record.email_verified_at = user.email_verified_at
        record.phone_verified_at = user.phone_verified_at
        record.last_login_at = user.last_login_at
        record.failed_login_count = user.failed_login_count
        record.updated_at = user.updated_at

        known = {(item.provider, item.subject) for item in record.identities}
        for identity in user.federated_identities:
            if (identity.provider.value, identity.subject) in known:
                continue
            record.identities.append(
                FederatedIdentityRecord(
                    user_id=user.id,
                    provider=identity.provider.value,
                    subject=identity.subject,
                    email=identity.email.value,
                    created_at=identity.linked_at,
                    updated_at=identity.linked_at,
                )
            )
        await self._session.flush()


def _translate_unique_violation(exc: IntegrityError) -> Exception:
    """Map a unique-constraint violation back to the domain error for it.

    Matched on constraint name rather than message text, which is what makes
    this stable across Postgres versions and locales.
    """
    detail = str(exc.orig)
    if "uq_users_phone" in detail:
        return PhoneAlreadyRegisteredError()
    if "uq_users_email" in detail:
        return EmailAlreadyRegisteredError()
    return exc


def _to_domain(record: UserRecord) -> User:
    return User(
        id=UserId(record.id),
        tenant_id=TenantId(record.tenant_id),
        email=EmailAddress(record.email),
        # Bare constructor, like EmailAddress above: stored rows were normalised
        # on the way in, so this validates without re-normalising.
        phone=PhoneNumber(record.phone) if record.phone else None,
        display_name=record.display_name,
        status=UserStatus(record.status),
        roles=frozenset(Role(role) for role in record.roles),
        password_hash=record.password_hash,
        email_verified_at=_aware(record.email_verified_at),
        phone_verified_at=_aware(record.phone_verified_at),
        last_login_at=_aware(record.last_login_at),
        failed_login_count=record.failed_login_count,
        federated_identities=[
            FederatedIdentity(
                provider=AuthProvider(identity.provider),
                subject=identity.subject,
                email=EmailAddress(identity.email),
                linked_at=_aware(identity.created_at) or datetime.now(UTC),
            )
            for identity in record.identities
        ],
        created_at=_aware(record.created_at) or datetime.now(UTC),
        updated_at=_aware(record.updated_at) or datetime.now(UTC),
    )


def _aware(moment: datetime | None) -> datetime | None:
    """Guarantee UTC-aware datetimes leaving the persistence layer.

    Postgres returns aware values for timestamptz, but a driver or a test using
    SQLite can hand back naive ones, and naive datetimes compared against
    aware ones raise at runtime.
    """
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
