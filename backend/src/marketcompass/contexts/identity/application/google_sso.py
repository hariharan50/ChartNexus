"""Google sign-in.

Authorization Code flow with PKCE. The sequence is:

1. ``StartGoogleLogin`` mints ``state``/``nonce``/``code_verifier``, stores them
   server-side under ``state``, and hands back the Google URL.
2. The user authenticates at Google and returns with ``code`` and ``state``.
3. ``CompleteGoogleLogin`` consumes the stored entry (one use only), exchanges
   the code, verifies the id_token, and resolves it to a local account.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from marketcompass.contexts.identity.application.dto import (
    AuthenticationResult,
    RequestContextInput,
    UserView,
)
from marketcompass.contexts.identity.application.ports import (
    Clock,
    GoogleIdentityProvider,
    GoogleProfile,
    OAuthStateStore,
    UnitOfWork,
    UserRepository,
)
from marketcompass.contexts.identity.application.session_service import SessionService
from marketcompass.contexts.identity.domain.errors import (
    HostedDomainNotAllowedError,
    IdentityConflictError,
    OAuthProviderError,
    OAuthStateError,
)
from marketcompass.contexts.identity.domain.user import User
from marketcompass.shared_kernel.types.identifiers import TenantId, new_id


@dataclass(frozen=True, slots=True)
class GoogleAuthorizationView:
    authorization_url: str
    state: str


@dataclass(frozen=True, slots=True)
class StartGoogleLoginCommand:
    """``redirect_to`` is where the frontend wants to land afterwards."""

    redirect_to: str | None = None


@dataclass(frozen=True, slots=True)
class CompleteGoogleLoginCommand:
    code: str
    state: str
    context: RequestContextInput = field(default_factory=RequestContextInput)


@dataclass(frozen=True, slots=True)
class GoogleLoginPolicy:
    state_ttl_seconds: int
    allowed_hosted_domains: tuple[str, ...] = ()
    auto_provision: bool = True


class StartGoogleLogin:
    def __init__(
        self,
        *,
        provider: GoogleIdentityProvider,
        state_store: OAuthStateStore,
        policy: GoogleLoginPolicy,
    ) -> None:
        self._provider = provider
        self._state_store = state_store
        self._policy = policy

    async def __call__(self, command: StartGoogleLoginCommand) -> GoogleAuthorizationView:
        request = self._provider.build_authorization_request()
        await self._state_store.save(
            request.state,
            code_verifier=request.code_verifier,
            nonce=request.nonce,
            redirect_to=_safe_redirect(command.redirect_to),
            ttl_seconds=self._policy.state_ttl_seconds,
        )
        return GoogleAuthorizationView(
            authorization_url=request.authorization_url,
            state=request.state,
        )


class CompleteGoogleLogin:
    def __init__(
        self,
        *,
        provider: GoogleIdentityProvider,
        state_store: OAuthStateStore,
        users: UserRepository,
        sessions: SessionService,
        clock: Clock,
        uow: UnitOfWork,
        policy: GoogleLoginPolicy,
    ) -> None:
        self._provider = provider
        self._state_store = state_store
        self._users = users
        self._sessions = sessions
        self._clock = clock
        self._uow = uow
        self._policy = policy

    async def __call__(self, command: CompleteGoogleLoginCommand) -> AuthenticationResult:
        pending = await self._state_store.consume(command.state)
        if pending is None:
            # Unknown, expired, or already-used state. All three mean the same
            # thing to the user, and CSRF depends on not accepting any of them.
            raise OAuthStateError

        profile = await self._provider.exchange_code(
            code=command.code,
            code_verifier=pending.code_verifier,
            nonce=pending.nonce,
        )

        self._enforce_hosted_domain(profile)
        if not profile.email_verified:
            # Without this, anyone able to create an unverified Google account
            # for an address could take over the matching local account.
            raise OAuthProviderError("This Google account has no verified email address.")

        user, is_new = await self._resolve_user(profile)
        user.ensure_can_authenticate()

        now = self._clock.now()
        user.record_successful_login(now)
        await self._users.update(user)

        tokens = await self._sessions.start(user, command.context)
        await self._uow.commit()

        return AuthenticationResult(user=UserView.of(user), tokens=tokens, is_new_user=is_new)

    async def _resolve_user(self, profile: GoogleProfile) -> tuple[User, bool]:
        # The subject is the stable key: a user can change their Google email,
        # and the link must survive that.
        existing = await self._users.find_by_google_subject(profile.subject)
        if existing is not None:
            return existing, False

        by_email = await self._users.find_by_email(profile.email)
        if by_email is not None:
            # Same verified address, no link yet: attach this Google account to
            # the existing local one rather than creating a duplicate.
            now = self._clock.now()
            by_email.link_google_identity(subject=profile.subject, email=profile.email, now=now)
            by_email.mark_email_verified(now)
            return by_email, False

        if not self._policy.auto_provision:
            raise IdentityConflictError("No MarketCompass account matches this Google account.")

        now = self._clock.now()
        user = User.register_with_google(
            tenant_id=TenantId(new_id()),
            email=profile.email,
            display_name=profile.display_name,
            subject=profile.subject,
            now=now,
        )
        await self._users.add(user)
        return user, True

    def _enforce_hosted_domain(self, profile: GoogleProfile) -> None:
        allowed = self._policy.allowed_hosted_domains
        if not allowed:
            return
        # `hd` is asserted by Google for Workspace accounts; personal gmail.com
        # accounts have none, and must not pass a domain restriction.
        domain = profile.hosted_domain
        if domain is None or domain.lower() not in {item.lower() for item in allowed}:
            raise HostedDomainNotAllowedError(domain or profile.email.domain)


def _safe_redirect(target: str | None) -> str | None:
    """Only allow same-site relative paths.

    An absolute URL here would turn the callback into an open redirect, which is
    the classic way to make a phishing link look legitimate.
    """
    if not target:
        return None
    if not target.startswith("/") or target.startswith("//"):
        return None
    return target[:512]
