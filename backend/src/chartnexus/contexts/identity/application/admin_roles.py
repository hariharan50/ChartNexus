"""Granting and revoking the platform ``admin`` role.

Every sign-up is ``owner`` of its own workspace, which is a normal user. Admin
is a role added on top, and this module is the only code that adds or removes
it. Nothing on the web reaches it: its only caller is the ``chartnexus-admin``
command, so becoming an admin requires a shell on the server, which is already
the most privileged position there is. A stolen web session or an API bug
cannot promote anyone.

Rules enforced here rather than trusted to the operator:

* only an **active** account can be granted admin;
* never more than ``max_admins`` admins at once;
* the **last** admin cannot be revoked, so the platform cannot be locked out
  by accident;
* revoking signs the account out everywhere, so a demoted admin does not keep
  a session minted while they were one. (The admin API also re-reads the role
  from the database on every request, so access ends at once either way.)

Every change is written to the audit trail with who ran it and from where.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from chartnexus.contexts.identity.domain.refresh_session import SessionRevocationReason
from chartnexus.contexts.identity.domain.user import User
from chartnexus.contexts.identity.domain.value_objects import EmailAddress, Role, UserStatus
from chartnexus.shared_kernel.domain.errors import ValidationError
from chartnexus.shared_kernel.types.identifiers import UserId


class AdminDirectory(Protocol):
    async def find_by_email(self, email: EmailAddress) -> User | None: ...

    async def update(self, user: User) -> None: ...

    async def list_with_role(self, role: str) -> list[User]: ...


class SessionRevoker(Protocol):
    async def revoke_all_for_user(
        self, user_id: UserId, reason: SessionRevocationReason, now: datetime
    ) -> int: ...


class AdminAuditTrail(Protocol):
    async def append(self, entry: dict[str, str]) -> None: ...


class Transaction(Protocol):
    async def commit(self) -> None: ...


class AdminRoleError(ValidationError):
    """A grant or revoke that the rules above refuse."""


@dataclass(frozen=True, slots=True)
class AdminChange:
    email: str
    changed: bool
    sessions_revoked: int = 0
    email_verified: bool = True


class AdminRoles:
    def __init__(
        self,
        *,
        users: AdminDirectory,
        sessions: SessionRevoker,
        audit: AdminAuditTrail,
        transaction: Transaction,
        max_admins: int,
        now: datetime,
        actor: str,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._audit = audit
        self._transaction = transaction
        self._max = max_admins
        self._now = now
        self._actor = actor

    async def list_admins(self) -> list[User]:
        return sorted(
            await self._users.list_with_role(Role.ADMIN.value), key=lambda user: user.email.value
        )

    async def grant(self, raw_email: str) -> AdminChange:
        user = await self._require_user(raw_email)
        if user.has_role(Role.ADMIN):
            return AdminChange(email=user.email.value, changed=False)
        if user.status is not UserStatus.ACTIVE:
            raise AdminRoleError(
                f"{user.email.value} is {user.status.value}; only an active account "
                "can be made an admin."
            )
        admins = await self._users.list_with_role(Role.ADMIN.value)
        if len(admins) >= self._max:
            raise AdminRoleError(
                f"There are already {len(admins)} admins (the limit is {self._max}). "
                "Revoke one first, or raise CN_AUTH_ADMIN_MAX_COUNT."
            )

        user.roles = frozenset({*user.roles, Role.ADMIN})
        user.updated_at = self._now
        await self._users.update(user)
        # Sign out existing sessions so the next sign-in carries the new role
        # everywhere, instead of half the user's tabs knowing and half not.
        revoked = await self._sessions.revoke_all_for_user(
            user.id, SessionRevocationReason.ADMIN_REVOKED, self._now
        )
        await self._transaction.commit()
        await self._record("grant", user)
        return AdminChange(
            email=user.email.value,
            changed=True,
            sessions_revoked=revoked,
            email_verified=user.is_email_verified,
        )

    async def revoke(self, raw_email: str) -> AdminChange:
        user = await self._require_user(raw_email)
        if not user.has_role(Role.ADMIN):
            return AdminChange(email=user.email.value, changed=False)
        admins = await self._users.list_with_role(Role.ADMIN.value)
        if len(admins) <= 1:
            raise AdminRoleError(
                f"{user.email.value} is the last admin. Grant another account first, "
                "so the platform is never left without one."
            )

        user.roles = frozenset(role for role in user.roles if role is not Role.ADMIN) or frozenset(
            {Role.OWNER}
        )
        user.updated_at = self._now
        await self._users.update(user)
        revoked = await self._sessions.revoke_all_for_user(
            user.id, SessionRevocationReason.ADMIN_REVOKED, self._now
        )
        await self._transaction.commit()
        await self._record("revoke", user)
        return AdminChange(email=user.email.value, changed=True, sessions_revoked=revoked)

    async def _require_user(self, raw_email: str) -> User:
        user = await self._users.find_by_email(EmailAddress.parse(raw_email))
        if user is None:
            raise AdminRoleError("No account has that email address.")
        return user

    async def _record(self, action: str, user: User) -> None:
        await self._audit.append(
            {
                "at": self._now.isoformat(),
                "action": f"admin.{action}",
                "user_id": str(user.id),
                "email": user.email.value,
                "actor": self._actor,
            }
        )
