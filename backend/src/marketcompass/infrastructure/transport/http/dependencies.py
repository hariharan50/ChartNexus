"""Shared FastAPI plumbing.

Request-scoped database sessions, the unit-of-work adapter, and the
authenticated principal — needed by every context's router.

This lives in transport infrastructure rather than in the identity context on
purpose. A bounded context may not import another, so if `market_data` had to
reach into `contexts.identity.api` for `CurrentPrincipal`, the boundary would be
broken by the framework wiring alone. Authenticating an HTTP request is
transport's job; identity only owns the rules behind the token.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.infrastructure.observability.request_context import bind_principal
from marketcompass.infrastructure.security.cookie_manager import CSRF_HEADER, CookieManager
from marketcompass.shared_kernel.domain.errors import AuthenticationError, AuthorizationError
from marketcompass.shared_kernel.types.identifiers import SessionId, TenantId, UserId

if TYPE_CHECKING:
    from marketcompass.contexts.identity.application.ports import AccessTokenClaims

# Methods that cannot change state do not need CSRF protection, and requiring it
# on them would break ordinary navigation.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_container(request: Request) -> Any:
    """The process-lifetime container, attached during lifespan startup.

    Typed loosely because infrastructure must not import the composition root.
    """
    return request.app.state.container


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One database session per request, committed by the use case's UoW."""
    container = get_container(request)
    async with container.database.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


class SessionUnitOfWork:
    """Adapts an ``AsyncSession`` to the ``UnitOfWork`` port.

    Every context declares its own structural ``UnitOfWork`` protocol; this one
    adapter satisfies all of them.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller, as proven by the access token."""

    claims: AccessTokenClaims

    @property
    def user_id(self) -> UserId:
        return self.claims.subject

    @property
    def tenant_id(self) -> TenantId:
        return self.claims.tenant_id

    @property
    def session_id(self) -> SessionId:
        return self.claims.session_id

    def require_role(self, *roles: str) -> None:
        if not self.claims.roles.intersection(roles):
            raise AuthorizationError("You do not have permission to perform this action.")


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


async def get_principal(request: Request) -> Principal:
    """Authenticate from either transport.

    The Bearer header wins: a client that sends one is explicitly not relying on
    ambient cookie authority, so it is exempt from the CSRF check.
    """
    container = get_container(request)
    cookies = CookieManager(auth=container.settings.auth, security=container.settings.security)

    token = _extract_bearer(request)
    from_cookie = False
    if token is None:
        token = cookies.read_access_token(request)
        from_cookie = token is not None

    if not token:
        raise AuthenticationError("Authentication is required.")

    if from_cookie and request.method not in _SAFE_METHODS and not cookies.verify_csrf(request):
        raise AuthorizationError(
            f"Missing or invalid {CSRF_HEADER} header.",
            header=CSRF_HEADER,
        )

    claims = container.access_tokens.decode(token)
    bind_principal(tenant_id=str(claims.tenant_id), user_id=str(claims.subject))
    return Principal(claims=claims)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


async def get_optional_principal(request: Request) -> Principal | None:
    """For endpoints that behave differently when signed in but do not require it."""
    try:
        return await get_principal(request)
    except (AuthenticationError, AuthorizationError):
        return None
