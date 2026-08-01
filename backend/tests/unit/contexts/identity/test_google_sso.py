"""Google sign-in: account resolution, linking, and the checks that guard it."""

from __future__ import annotations

import pytest

from marketcompass.contexts.identity.application.google_sso import (
    CompleteGoogleLogin,
    CompleteGoogleLoginCommand,
    GoogleLoginPolicy,
    StartGoogleLogin,
    StartGoogleLoginCommand,
)
from marketcompass.contexts.identity.application.session_service import (
    SessionPolicy,
    SessionService,
)
from marketcompass.contexts.identity.domain.errors import (
    AccountSuspendedError,
    HostedDomainNotAllowedError,
    IdentityConflictError,
    OAuthProviderError,
    OAuthStateError,
)
from marketcompass.contexts.identity.domain.user import User
from marketcompass.contexts.identity.domain.value_objects import (
    AuthProvider,
    EmailAddress,
    UserStatus,
)
from marketcompass.infrastructure.security.token_signer import JwtAccessTokenIssuer
from marketcompass.shared_kernel.types.identifiers import TenantId, new_id
from tests.unit.contexts.identity.conftest import (
    START,
    FakeGoogleProvider,
    FakeStateStore,
    google_profile,
)

pytestmark = pytest.mark.unit

EMAIL = "person@example.com"


@pytest.fixture
def provider() -> FakeGoogleProvider:
    return FakeGoogleProvider(profile=google_profile())


@pytest.fixture
def state_store() -> FakeStateStore:
    return FakeStateStore()


@pytest.fixture
def policy() -> GoogleLoginPolicy:
    return GoogleLoginPolicy(state_ttl_seconds=600)


@pytest.fixture
def start(provider, state_store, policy) -> StartGoogleLogin:  # type: ignore[no-untyped-def]
    return StartGoogleLogin(provider=provider, state_store=state_store, policy=policy)


@pytest.fixture
def complete(
    provider,
    state_store,
    users,
    sessions_repo,
    clock,
    uow,
    policy,
    auth_settings,
    security_settings,
):  # type: ignore[no-untyped-def]
    return CompleteGoogleLogin(
        provider=provider,
        state_store=state_store,
        users=users,
        sessions=SessionService(
            sessions=sessions_repo,
            tokens=JwtAccessTokenIssuer(auth_settings, security_settings),
            clock=clock,
            policy=SessionPolicy(
                refresh_ttl_seconds=3600, reuse_grace_seconds=10, max_active_sessions=5
            ),
            uow=uow,
        ),
        clock=clock,
        uow=uow,
        policy=policy,
    )


async def _begin(start: StartGoogleLogin, redirect_to: str | None = None) -> str:
    view = await start(StartGoogleLoginCommand(redirect_to=redirect_to))
    return view.state


# --- authorization step ----------------------------------------------------


async def test_authorize_returns_a_url_and_stores_the_pending_request(start, state_store):  # type: ignore[no-untyped-def]
    view = await start(StartGoogleLoginCommand())

    assert view.authorization_url.startswith("https://accounts.google.com/")
    assert view.state in state_store.entries
    # The PKCE verifier stays server-side; only the challenge goes to Google.
    assert state_store.entries[view.state].code_verifier


@pytest.mark.parametrize(
    "target",
    ["https://evil.example.com/steal", "//evil.example.com", "javascript:alert(1)"],
)
async def test_absolute_redirect_targets_are_discarded(start, state_store, target):  # type: ignore[no-untyped-def]
    """Otherwise the callback becomes an open redirect."""
    state = await _begin(start, redirect_to=target)
    assert state_store.entries[state].redirect_to is None


async def test_relative_redirect_target_is_kept(start, state_store):  # type: ignore[no-untyped-def]
    state = await _begin(start, redirect_to="/options/gamma-exposure")
    assert state_store.entries[state].redirect_to == "/options/gamma-exposure"


# --- callback step ---------------------------------------------------------


async def test_first_sign_in_provisions_a_verified_account(complete, start, users):  # type: ignore[no-untyped-def]
    state = await _begin(start)
    result = await complete(CompleteGoogleLoginCommand(code="auth-code", state=state))

    assert result.is_new_user
    assert result.user.email == EMAIL
    assert result.user.email_verified
    # No password was set, which is what makes password login refuse politely.
    assert not result.user.has_password
    assert result.user.linked_providers == ("google",)
    assert result.tokens.access_token


async def test_returning_user_is_matched_by_subject_not_email(complete, start, users, clock):  # type: ignore[no-untyped-def]
    """The Google account's email can change; its `sub` cannot."""
    state = await _begin(start)
    first = await complete(CompleteGoogleLoginCommand(code="c1", state=state))

    stored = await users.get(first.user.id)
    assert stored is not None
    stored.email = EmailAddress.parse("renamed@example.com")

    state = await _begin(start)
    second = await complete(CompleteGoogleLoginCommand(code="c2", state=state))

    assert not second.is_new_user
    assert second.user.id == first.user.id
    assert len(users.users) == 1


async def test_google_links_to_an_existing_password_account(complete, start, users, hasher):  # type: ignore[no-untyped-def]
    """Same verified address: link, do not create a second account."""
    existing = User.register_with_password(
        tenant_id=TenantId(new_id()),
        email=EmailAddress.parse(EMAIL),
        display_name="Person",
        password_hash=hasher.hash("some-password"),
        now=START,
        requires_verification=False,
    )
    users.users[existing.id] = existing

    state = await _begin(start)
    result = await complete(CompleteGoogleLoginCommand(code="code", state=state))

    assert not result.is_new_user
    assert result.user.id == existing.id
    assert len(users.users) == 1
    # The account keeps its password and gains a provider.
    assert result.user.has_password
    assert result.user.linked_providers == ("google",)
    assert result.user.email_verified


async def test_unverified_google_email_is_refused(complete, start, provider):  # type: ignore[no-untyped-def]
    """Otherwise an unverified Google account could claim someone's address."""
    provider.profile = google_profile(verified=False)
    state = await _begin(start)

    with pytest.raises(OAuthProviderError):
        await complete(CompleteGoogleLoginCommand(code="code", state=state))


async def test_unknown_state_is_refused(complete):  # type: ignore[no-untyped-def]
    with pytest.raises(OAuthStateError):
        await complete(CompleteGoogleLoginCommand(code="code", state="never-issued"))


async def test_state_cannot_be_replayed(complete, start):  # type: ignore[no-untyped-def]
    state = await _begin(start)
    await complete(CompleteGoogleLoginCommand(code="code", state=state))

    with pytest.raises(OAuthStateError):
        await complete(CompleteGoogleLoginCommand(code="code", state=state))


async def test_the_code_is_not_exchanged_when_the_state_is_bad(complete, provider):  # type: ignore[no-untyped-def]
    with pytest.raises(OAuthStateError):
        await complete(CompleteGoogleLoginCommand(code="code", state="bogus"))
    assert provider.exchanges == 0


async def test_suspended_account_cannot_sign_in_through_google(complete, start, users, hasher):  # type: ignore[no-untyped-def]
    existing = User.register_with_password(
        tenant_id=TenantId(new_id()),
        email=EmailAddress.parse(EMAIL),
        display_name="Person",
        password_hash=hasher.hash("pw"),
        now=START,
        requires_verification=False,
    )
    existing.status = UserStatus.SUSPENDED
    users.users[existing.id] = existing

    state = await _begin(start)
    with pytest.raises(AccountSuspendedError):
        await complete(CompleteGoogleLoginCommand(code="code", state=state))


# --- hosted domain restriction ---------------------------------------------


async def test_workspace_domain_restriction_admits_the_allowed_domain(
    provider, state_store, users, sessions_repo, clock, uow, auth_settings, security_settings
):  # type: ignore[no-untyped-def]
    restricted = GoogleLoginPolicy(
        state_ttl_seconds=600, allowed_hosted_domains=("marketcompass.app",)
    )
    provider.profile = google_profile(
        email="analyst@marketcompass.app", hosted_domain="marketcompass.app"
    )
    start = StartGoogleLogin(provider=provider, state_store=state_store, policy=restricted)
    complete = CompleteGoogleLogin(
        provider=provider,
        state_store=state_store,
        users=users,
        sessions=SessionService(
            sessions=sessions_repo,
            tokens=JwtAccessTokenIssuer(auth_settings, security_settings),
            clock=clock,
            policy=SessionPolicy(
                refresh_ttl_seconds=3600, reuse_grace_seconds=10, max_active_sessions=5
            ),
            uow=uow,
        ),
        clock=clock,
        uow=uow,
        policy=restricted,
    )

    state = await _begin(start)
    result = await complete(CompleteGoogleLoginCommand(code="code", state=state))
    assert result.user.email == "analyst@marketcompass.app"


async def test_personal_account_is_refused_when_a_domain_is_required(
    provider, state_store, users, sessions_repo, clock, uow, auth_settings, security_settings
):  # type: ignore[no-untyped-def]
    """A gmail.com account has no `hd` claim and must not slip through."""
    restricted = GoogleLoginPolicy(
        state_ttl_seconds=600, allowed_hosted_domains=("marketcompass.app",)
    )
    provider.profile = google_profile(email="someone@gmail.com", hosted_domain=None)
    start = StartGoogleLogin(provider=provider, state_store=state_store, policy=restricted)
    complete = CompleteGoogleLogin(
        provider=provider,
        state_store=state_store,
        users=users,
        sessions=SessionService(
            sessions=sessions_repo,
            tokens=JwtAccessTokenIssuer(auth_settings, security_settings),
            clock=clock,
            policy=SessionPolicy(
                refresh_ttl_seconds=3600, reuse_grace_seconds=10, max_active_sessions=5
            ),
            uow=uow,
        ),
        clock=clock,
        uow=uow,
        policy=restricted,
    )

    state = await _begin(start)
    with pytest.raises(HostedDomainNotAllowedError):
        await complete(CompleteGoogleLoginCommand(code="code", state=state))


# --- aggregate rules -------------------------------------------------------


async def test_a_second_google_account_cannot_hijack_a_link(hasher) -> None:  # type: ignore[no-untyped-def]
    user = User.register_with_google(
        tenant_id=TenantId(new_id()),
        email=EmailAddress.parse(EMAIL),
        display_name="Person",
        subject="google-original",
        now=START,
    )

    with pytest.raises(IdentityConflictError):
        user.link_google_identity(
            subject="google-attacker", email=EmailAddress.parse(EMAIL), now=START
        )

    identity = user.identity_for(AuthProvider.GOOGLE)
    assert identity is not None
    assert identity.subject == "google-original"


async def test_relinking_the_same_google_account_is_idempotent() -> None:
    user = User.register_with_google(
        tenant_id=TenantId(new_id()),
        email=EmailAddress.parse(EMAIL),
        display_name="Person",
        subject="google-1",
        now=START,
    )
    user.link_google_identity(subject="google-1", email=EmailAddress.parse(EMAIL), now=START)
    assert len(user.federated_identities) == 1
