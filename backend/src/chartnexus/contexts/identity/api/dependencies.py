"""FastAPI wiring for the identity context.

Two things live here: the per-request assembly of use cases (repositories need
the request's database session), and the authentication dependency every other
context will import to protect its routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from chartnexus.contexts.identity.application.authenticate import (
    LoginWithPassword,
    RegisterUser,
    RegistrationPolicy,
)
from chartnexus.contexts.identity.application.google_sso import (
    CompleteGoogleLogin,
    GoogleLoginPolicy,
    StartGoogleLogin,
)
from chartnexus.contexts.identity.application.ports import (
    AuthorizationRequest,
    GoogleIdentityProvider,
    GoogleProfile,
)
from chartnexus.contexts.identity.application.session_service import (
    SessionPolicy,
    SessionService,
)
from chartnexus.contexts.identity.application.sessions import (
    GetCurrentUser,
    ListSessions,
    Logout,
    LogoutEverywhere,
    RefreshSessionTokens,
)
from chartnexus.contexts.identity.domain.errors import OAuthProviderError
from chartnexus.contexts.identity.domain.password_policy import PasswordPolicy
from chartnexus.infrastructure.cache.redis.rate_limiter import (
    RateLimitPolicy,
    RedisLoginRateLimiter,
)
from chartnexus.infrastructure.cache.redis.session_store import RedisOAuthStateStore
from chartnexus.infrastructure.persistence.postgresql.repositories.identity.refresh_session_repository import (
    SqlAlchemyRefreshSessionRepository,
)
from chartnexus.infrastructure.persistence.postgresql.repositories.identity.user_repository import (
    SqlAlchemyUserRepository,
)
from chartnexus.infrastructure.security.cookie_manager import CookieManager
from chartnexus.infrastructure.time.clock import SystemClock
from chartnexus.infrastructure.transport.http.dependencies import (
    CurrentPrincipal,
    Principal,
    SessionUnitOfWork,
    get_container,
    get_optional_principal,
    get_principal,
    get_session,
)

_UNCONFIGURED = "Google sign-in is not configured on this server."


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
    uow = SessionUnitOfWork(session)

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


# Re-exported so existing identity imports keep working; the definitions live in
# transport infrastructure because every context needs them.
__all__ = [
    "CurrentPrincipal",
    "IdentityServices",
    "Principal",
    "Services",
    "SessionUnitOfWork",
    "get_container",
    "get_optional_principal",
    "get_principal",
    "get_session",
]
