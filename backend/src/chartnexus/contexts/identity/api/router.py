"""Authentication endpoints.

Every route that establishes or ends a session writes cookies *and* returns the
tokens in the body, so the same endpoint serves the browser app and a script.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status

from chartnexus.contexts.identity.api.dependencies import CurrentPrincipal, Services
from chartnexus.contexts.identity.api.schemas import (
    AuthenticationResponse,
    GoogleAuthorizeRequest,
    GoogleAuthorizeResponse,
    GoogleCallbackRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    RevokedSessionsResponse,
    SessionResponse,
    UserResponse,
)
from chartnexus.contexts.identity.application.authenticate import (
    LoginCommand,
    RegisterUserCommand,
)
from chartnexus.contexts.identity.application.dto import (
    AuthenticationResult,
    RequestContextInput,
)
from chartnexus.contexts.identity.application.google_sso import (
    CompleteGoogleLoginCommand,
    StartGoogleLoginCommand,
)
from chartnexus.contexts.identity.application.sessions import LogoutCommand, RefreshCommand
from chartnexus.contexts.identity.domain.errors import SessionExpiredError

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/register",
    response_model=AuthenticationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    responses={
        409: {"description": "The email address is already registered"},
        422: {"description": "The password does not meet the policy"},
    },
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    services: Services,
) -> AuthenticationResponse:
    result = await services.register(
        RegisterUserCommand(
            email=str(payload.email),
            password=payload.password,
            phone=payload.phone,
            display_name=payload.display_name,
            context=_context_of(request),
        )
    )
    return _authenticated(result, response, services)


@router.post(
    "/login",
    response_model=AuthenticationResponse,
    summary="Sign in with an email address and password",
    responses={
        401: {"description": "Invalid credentials, or the account uses SSO"},
        429: {"description": "Too many failed attempts"},
    },
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    services: Services,
) -> AuthenticationResponse:
    result = await services.login(
        LoginCommand(
            identifier=payload.identifier,
            password=payload.password,
            context=_context_of(request),
        )
    )
    return _authenticated(result, response, services)


@router.post(
    "/refresh",
    response_model=AuthenticationResponse,
    summary="Exchange a refresh token for a new token pair",
    responses={401: {"description": "The session has expired or was revoked"}},
)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    services: Services,
) -> AuthenticationResponse:
    # Body first so a non-browser client can refresh without cookies; the
    # browser sends nothing and falls through to the cookie.
    token = payload.refresh_token or services.cookies.read_refresh_token(request)
    if not token:
        raise SessionExpiredError("No refresh token was supplied.")

    result = await services.refresh(
        RefreshCommand(refresh_token=token, context=_context_of(request))
    )
    return _authenticated(result, response, services)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="End the current session",
)
async def logout(
    payload: LogoutRequest,
    request: Request,
    response: Response,
    services: Services,
) -> MessageResponse:
    token = payload.refresh_token or services.cookies.read_refresh_token(request)
    await services.logout(LogoutCommand(refresh_token=token))
    # Cookies are cleared even when no token matched, so a client holding a
    # stale cookie is not left in a half-signed-in state.
    services.cookies.clear(response)
    return MessageResponse(message="Signed out.")


@router.post(
    "/logout-all",
    response_model=RevokedSessionsResponse,
    summary="End every session on every device",
)
async def logout_all(
    principal: CurrentPrincipal,
    response: Response,
    services: Services,
) -> RevokedSessionsResponse:
    revoked = await services.logout_everywhere(principal.user_id)
    services.cookies.clear(response)
    return RevokedSessionsResponse(revoked=revoked)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="The signed-in user",
    responses={401: {"description": "Not signed in"}},
)
async def me(principal: CurrentPrincipal, services: Services) -> UserResponse:
    return UserResponse.of(await services.current_user(principal.user_id))


@router.get(
    "/sessions",
    response_model=list[SessionResponse],
    summary="List active sessions",
)
async def list_sessions(
    principal: CurrentPrincipal,
    services: Services,
) -> list[SessionResponse]:
    sessions = await services.list_sessions(principal.user_id, principal.session_id)
    return [SessionResponse.of(session) for session in sessions]


# --- Google SSO ------------------------------------------------------------


@router.post(
    "/google/authorize",
    response_model=GoogleAuthorizeResponse,
    summary="Begin Google sign-in",
    description=(
        "Returns the Google consent URL. The client redirects the browser there; "
        "Google returns to the configured redirect URI with `code` and `state`, "
        "which the client posts to `/auth/google/callback`."
    ),
)
async def google_authorize(
    payload: GoogleAuthorizeRequest,
    services: Services,
) -> GoogleAuthorizeResponse:
    view = await services.start_google_login(
        StartGoogleLoginCommand(redirect_to=payload.redirect_to)
    )
    return GoogleAuthorizeResponse(authorization_url=view.authorization_url, state=view.state)


@router.post(
    "/google/callback",
    response_model=AuthenticationResponse,
    summary="Complete Google sign-in",
    responses={
        401: {"description": "Google rejected the exchange, or the email is unverified"},
        422: {"description": "The state parameter is unknown or expired"},
    },
)
async def google_callback(
    payload: GoogleCallbackRequest,
    request: Request,
    response: Response,
    services: Services,
) -> AuthenticationResponse:
    result = await services.complete_google_login(
        CompleteGoogleLoginCommand(
            code=payload.code,
            state=payload.state,
            context=_context_of(request),
        )
    )
    return _authenticated(result, response, services)


# --- helpers ---------------------------------------------------------------


def _authenticated(
    result: AuthenticationResult,
    response: Response,
    services: Services,
) -> AuthenticationResponse:
    csrf_token = services.cookies.issue(response, result.tokens, now=datetime.now(UTC))
    return AuthenticationResponse.of(result, csrf_token=csrf_token)


def _context_of(request: Request) -> RequestContextInput:
    return RequestContextInput(
        user_agent=request.headers.get("User-Agent"),
        ip_address=_client_ip(request),
    )


def _client_ip(request: Request) -> str | None:
    """The client address, trusting the proxy only for the first hop.

    ``X-Forwarded-For`` is client-controlled and accumulates left to right, so
    the leftmost entry is whatever the client claimed. It is recorded for
    display, never used for an authorisation decision.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return request.client.host if request.client else None
