"""FastAPI wiring for the identity context.

Two things live here: the per-request assembly of use cases (repositories need
the request's database session), and the authentication dependency every other
context will import to protect its routes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.identity.application.authenticate import (
    LoginWithPassword,
    RegisterUser,
    RegistrationPolicy,
)
from marketcompass.contexts.identity.application.google_sso import (
    CompleteGoogleLogin,
    GoogleLoginPolicy,
    StartGoogleLogin,
)
from marketcompass.contexts.identity.application.ports import (
    AccessTokenClaims,
    AuthorizationRequest,
    GoogleIdentityProvider,
    GoogleProfile,
)
from marketcompass.contexts.identity.application.session_service import (
    SessionPolicy,
    SessionService,
)
from marketcompass.contexts.identity.application.sessions import (
    GetCurrentUser,
    ListSessions,
    Logout,
    LogoutEverywhere,
    RefreshSessionTokens,
)
from marketcompass.contexts.identity.domain.errors import OAuthProviderError
from marketcompass.contexts.identity.domain.password_policy import PasswordPolicy
from marketcompass.infrastructure.cache.redis.rate_limiter import (
    RateLimitPolicy,
    RedisLoginRateLimiter,
)
from marketcompass.infrastructure.cache.redis.session_store import RedisOAuthStateStore
from marketcompass.infrastructure.observability.request_context import bind_principal
from marketcompass.infrastructure.persistence.postgresql.repositories.identity.refresh_session_repository import (
    SqlAlchemyRefreshSessionRepository,
)
from marketcompass.infrastructure.persistence.postgresql.repositories.identity.user_repository import (
    SqlAlchemyUserRepository,
)
from marketcompass.infrastructure.security.cookie_manager import CSRF_HEADER, CookieManager
from marketcompass.infrastructure.time.clock import SystemClock
from marketcompass.shared_kernel.domain.errors import AuthenticationError, AuthorizationError

# Methods that cannot change state do not need CSRF protection, and requiring it
# on them would break ordinary navigation.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_UNCONFIGURED = "Google sign-in is not configured on this server."


def get_container(request: Request):  # type: ignore[no-untyped-def]
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


class _SessionUnitOfWork:
    """Adapts an ``AsyncSession`` to the ``UnitOfWork`` port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


@dataclass(slots=True)
class IdentityServices:
    """Everything the auth router needs, assembled once per request."""

    register: RegisterUser
    login: LoginWithPassword
    refresh: RefreshSessionTokens
    logout: Logout
    logout_everywhere: LogoutEverywhere
    current_user: GetCurrentUser
    list_sessions: ListSessions
    start_google_login: StartGoogleLogin
    complete_google_login: CompleteGoogleLogin
    cookies: CookieManager


def build_identity_services(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IdentityServices:
    container = get_container(request)
    settings = container.settings
    clock = SystemClock()

    users = SqlAlchemyUserRepository(session)
    refresh_sessions = SqlAlchemyRefreshSessionRepository(session)
    uow = _SessionUnitOfWork(session)

    session_service = SessionService(
        sessions=refresh_sessions,
        tokens=container.access_tokens,
        clock=clock,
        policy=SessionPolicy(
            refresh_ttl_seconds=settings.auth.refresh_token_ttl_seconds,
            reuse_grace_seconds=settings.auth.refresh_reuse_grace_seconds,
            max_active_sessions=settings.auth.max_active_sessions_per_user,
        ),
        uow=uow,
    )

    rate_limiter = RedisLoginRateLimiter(
        container.redis,
        RateLimitPolicy(
            max_attempts=settings.auth.login_max_attempts,
            window_seconds=settings.auth.login_attempt_window_seconds,
            lockout_seconds=settings.auth.login_lockout_seconds,
        ),
    )

    google_policy = GoogleLoginPolicy(
        state_ttl_seconds=settings.google.state_ttl_seconds,
        allowed_hosted_domains=settings.google.allowed_hosted_domains,
    )
    state_store = RedisOAuthStateStore(container.redis)

    return IdentityServices(
        register=RegisterUser(
            users=users,
            hasher=container.password_hasher,
            sessions=session_service,
            clock=clock,
            uow=uow,
            password_policy=PasswordPolicy(min_length=settings.security.password_min_length),
            registration_policy=RegistrationPolicy(
                enabled=settings.auth.registration_enabled,
                require_email_verification=settings.auth.require_email_verification,
            ),
        ),
        login=LoginWithPassword(
            users=users,
            hasher=container.password_hasher,
            sessions=session_service,
            clock=clock,
            uow=uow,
            rate_limiter=rate_limiter,
        ),
        refresh=RefreshSessionTokens(users=users, sessions=session_service, uow=uow),
        logout=Logout(sessions=session_service, uow=uow),
        logout_everywhere=LogoutEverywhere(users=users, sessions=session_service, uow=uow),
        current_user=GetCurrentUser(users=users),
        list_sessions=ListSessions(sessions_repository=refresh_sessions),
        start_google_login=StartGoogleLogin(
            provider=_require_google(container),
            state_store=state_store,
            policy=google_policy,
        ),
        complete_google_login=CompleteGoogleLogin(
            provider=_require_google(container),
            state_store=state_store,
            users=users,
            sessions=session_service,
            clock=clock,
            uow=uow,
            policy=google_policy,
        ),
        cookies=CookieManager(auth=settings.auth, security=settings.security),
    )


def _require_google(container: object) -> GoogleIdentityProvider:
    google = getattr(container, "google_oauth", None)
    if google is None:
        # Constructed lazily so the rest of the API still runs with no Google
        # credentials configured; only the two Google routes fail.
        return _UnconfiguredGoogleProvider()
    return google  # type: ignore[no-any-return]


class _UnconfiguredGoogleProvider:
    """Stands in for the real client so the routes fail with a clear message
    rather than an AttributeError. Mirrors the port's signature exactly."""

    def build_authorization_request(
        self,
        *,
        redirect_uri: str | None = None,  # noqa: ARG002 — mirrors the port
    ) -> AuthorizationRequest:
        raise OAuthProviderError(_UNCONFIGURED)

    async def exchange_code(
        self,
        *,
        code: str,  # noqa: ARG002 — mirrors the port
        code_verifier: str,  # noqa: ARG002
        nonce: str,  # noqa: ARG002
        redirect_uri: str | None = None,  # noqa: ARG002
    ) -> GoogleProfile:
        raise OAuthProviderError(_UNCONFIGURED)


Services = Annotated[IdentityServices, Depends(build_identity_services)]


# --- authentication --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller, as proven by the access token."""

    claims: AccessTokenClaims

    @property
    def user_id(self):  # type: ignore[no-untyped-def]
        return self.claims.subject

    @property
    def tenant_id(self):  # type: ignore[no-untyped-def]
        return self.claims.tenant_id

    @property
    def session_id(self):  # type: ignore[no-untyped-def]
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
