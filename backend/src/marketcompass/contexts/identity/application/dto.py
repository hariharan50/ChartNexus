"""Data crossing the application boundary.

Plain dataclasses, not pydantic models: the HTTP schemas in ``api/schemas.py``
own serialisation, and the use cases stay usable from a CLI or a task without
dragging FastAPI along.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from marketcompass.contexts.identity.domain.user import User
from marketcompass.shared_kernel.types.identifiers import SessionId, TenantId, UserId


@dataclass(frozen=True, slots=True)
class RequestContextInput:
    """Where the request came from — recorded on the session for audit."""

    user_agent: str | None = None
    ip_address: str | None = None


@dataclass(frozen=True, slots=True)
class UserView:
    id: UserId
    tenant_id: TenantId
    email: str
    phone: str | None
    display_name: str
    status: str
    roles: tuple[str, ...]
    email_verified: bool
    has_password: bool
    linked_providers: tuple[str, ...]
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def of(cls, user: User) -> UserView:
        return cls(
            id=user.id,
            tenant_id=user.tenant_id,
            email=user.email.value,
            phone=user.phone.value if user.phone else None,
            display_name=user.display_name,
            status=user.status.value,
            roles=tuple(sorted(role.value for role in user.roles)),
            email_verified=user.is_email_verified,
            has_password=user.has_password,
            linked_providers=tuple(
                sorted(identity.provider.value for identity in user.federated_identities)
            ),
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )


@dataclass(frozen=True, slots=True)
class TokenPair:
    """Both tokens plus everything the transport needs to set cookies."""

    access_token: str
    access_token_expires_at: datetime
    access_token_expires_in: int
    refresh_token: str
    refresh_token_expires_at: datetime
    session_id: SessionId


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    user: UserView
    tokens: TokenPair
    is_new_user: bool = False


@dataclass(frozen=True, slots=True)
class SessionView:
    id: SessionId
    created_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip_address: str | None
    is_current: bool
