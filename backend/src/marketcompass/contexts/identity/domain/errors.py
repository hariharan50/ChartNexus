"""Identity-specific errors.

Each carries its own ``code`` so the frontend can react precisely — offer a
"resend verification" button, or send the user to Google — without parsing
human-readable messages.
"""

from __future__ import annotations

from marketcompass.shared_kernel.domain.errors import (
    AuthenticationError,
    ConflictError,
    ValidationError,
)


class InvalidCredentialsError(AuthenticationError):
    """Unknown identifier, or wrong password.

    One error for every case on purpose: distinguishing them turns the login
    endpoint into an account-existence oracle. The message names no particular
    identifier because sign-in accepts an email address or a phone number.
    """

    code = "invalid_credentials"

    def __init__(self) -> None:
        super().__init__("Those sign-in details do not match an account.")


class AccountSuspendedError(AuthenticationError):
    code = "account_suspended"

    def __init__(self) -> None:
        super().__init__("This account has been suspended.")


class AccountDisabledError(AuthenticationError):
    code = "account_disabled"

    def __init__(self) -> None:
        super().__init__("This account has been deactivated.")


class EmailNotVerifiedError(AuthenticationError):
    code = "email_unverified"

    def __init__(self) -> None:
        super().__init__("Verify your email address before signing in.")


class EmailAlreadyRegisteredError(ConflictError):
    code = "email_taken"

    def __init__(self) -> None:
        super().__init__("An account with this email address already exists.")


class PhoneAlreadyRegisteredError(ConflictError):
    code = "phone_taken"

    def __init__(self) -> None:
        super().__init__("An account with this phone number already exists.")


class PasswordLoginUnavailableError(AuthenticationError):
    """The account exists but was created through an identity provider."""

    code = "use_sso"

    def __init__(self, provider: str = "google") -> None:
        super().__init__(
            f"This account signs in with {provider.title()}. Continue with {provider.title()}.",
            provider=provider,
        )


class IdentityConflictError(ConflictError):
    code = "identity_conflict"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class SessionExpiredError(AuthenticationError):
    code = "session_expired"

    def __init__(self, message: str = "Your session has expired. Sign in again.") -> None:
        super().__init__(message)


class TokenReuseDetectedError(AuthenticationError):
    """A refresh token was presented twice.

    Either the token leaked or a client is misbehaving. Both are handled the
    same way: revoke the whole session family and make the user sign in again.
    """

    code = "session_revoked"

    def __init__(self) -> None:
        super().__init__("This session was revoked for security reasons. Sign in again.")


class RegistrationDisabledError(ConflictError):
    code = "registration_disabled"

    def __init__(self) -> None:
        super().__init__("Registration is currently closed.")


class OAuthStateError(ValidationError):
    """The OAuth callback did not match a pending authorization request."""

    code = "oauth_state_invalid"

    def __init__(self, message: str = "This sign-in link has expired. Start again.") -> None:
        super().__init__(message)


class OAuthProviderError(AuthenticationError):
    code = "oauth_failed"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class HostedDomainNotAllowedError(AuthenticationError):
    code = "domain_not_allowed"

    def __init__(self, domain: str) -> None:
        super().__init__(f"Accounts from {domain} are not permitted.", domain=domain)
