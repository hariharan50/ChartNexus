"""Granting and revoking platform admin: the rules the CLI relies on."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from chartnexus.contexts.identity.application.admin_roles import AdminRoleError, AdminRoles
from chartnexus.contexts.identity.domain.user import User
from chartnexus.contexts.identity.domain.value_objects import EmailAddress, Role, UserStatus
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId

NOW = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)


def _user(email: str, *, admin: bool = False, status: UserStatus = UserStatus.ACTIVE) -> User:
    roles = {Role.OWNER} | ({Role.ADMIN} if admin else set())
    return User(
        id=UserId(f"id-{email}"),
        tenant_id=TenantId(f"t-{email}"),
        email=EmailAddress.parse(email),
        display_name=email,
        status=status,
        roles=frozenset(roles),
        password_hash="x",
    )


class _Users:
    def __init__(self, *users: User) -> None:
        self.users = {user.email.value: user for user in users}

    async def find_by_email(self, email: EmailAddress) -> User | None:
        user = self.users.get(email.value)
        return replace(user) if user else None

    async def update(self, user: User) -> None:
        self.users[user.email.value] = user

    async def list_with_role(self, role: str) -> list[User]:
        return [user for user in self.users.values() if Role(role) in user.roles]


class _Sessions:
    def __init__(self) -> None:
        self.revoked: list[Any] = []

    async def revoke_all_for_user(self, user_id: Any, reason: Any, now: Any) -> int:
        self.revoked.append(user_id)
        return 2


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, str]] = []

    async def append(self, entry: dict[str, str]) -> None:
        self.entries.append(entry)


class _Tx:
    commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _roles(users: _Users, *, max_admins: int = 3) -> tuple[AdminRoles, _Sessions, _Audit]:
    sessions, audit = _Sessions(), _Audit()
    roles = AdminRoles(
        users=users,
        sessions=sessions,
        audit=audit,
        transaction=_Tx(),
        max_admins=max_admins,
        now=NOW,
        actor="cli:test@host",
    )
    return roles, sessions, audit


async def test_grant_adds_admin_signs_out_and_audits() -> None:
    users = _Users(_user("me@example.com"))
    roles, sessions, audit = _roles(users)

    change = await roles.grant("  ME@example.com ")

    assert change.changed and change.sessions_revoked == 2
    assert users.users["me@example.com"].has_role(Role.ADMIN)
    assert users.users["me@example.com"].has_role(Role.OWNER)  # still a normal user too
    assert sessions.revoked == [UserId("id-me@example.com")]
    assert audit.entries[0]["action"] == "admin.grant"
    assert audit.entries[0]["actor"] == "cli:test@host"


async def test_grant_is_idempotent() -> None:
    roles, _, audit = _roles(_Users(_user("me@example.com", admin=True)))
    assert not (await roles.grant("me@example.com")).changed
    assert audit.entries == []


async def test_grant_refuses_an_inactive_account() -> None:
    roles, _, _ = _roles(_Users(_user("x@example.com", status=UserStatus.SUSPENDED)))
    with pytest.raises(AdminRoleError, match="active"):
        await roles.grant("x@example.com")


async def test_grant_refuses_an_unknown_email() -> None:
    roles, _, _ = _roles(_Users())
    with pytest.raises(AdminRoleError, match="No account"):
        await roles.grant("nobody@example.com")


async def test_grant_respects_the_admin_limit() -> None:
    users = _Users(
        _user("a@example.com", admin=True),
        _user("b@example.com", admin=True),
        _user("c@example.com"),
    )
    roles, _, _ = _roles(users, max_admins=2)
    with pytest.raises(AdminRoleError, match="limit is 2"):
        await roles.grant("c@example.com")
    assert not users.users["c@example.com"].has_role(Role.ADMIN)


async def test_revoke_removes_admin_and_signs_out() -> None:
    users = _Users(_user("a@example.com", admin=True), _user("b@example.com", admin=True))
    roles, sessions, audit = _roles(users)

    change = await roles.revoke("b@example.com")

    assert change.changed
    assert users.users["b@example.com"].roles == frozenset({Role.OWNER})
    assert sessions.revoked == [UserId("id-b@example.com")]
    assert audit.entries[0]["action"] == "admin.revoke"


async def test_the_last_admin_can_never_be_revoked() -> None:
    users = _Users(_user("a@example.com", admin=True))
    roles, _, _ = _roles(users)
    with pytest.raises(AdminRoleError, match="last admin"):
        await roles.revoke("a@example.com")
    assert users.users["a@example.com"].has_role(Role.ADMIN)
