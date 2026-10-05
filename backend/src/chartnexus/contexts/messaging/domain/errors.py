"""Messaging domain errors.

Each subclasses a shared mapped error so the transport layer renders the right
status, and carries a stable ``code`` the frontend can branch on (plus ``field``
for the ones a form input can fix), mirroring the ai_settings error taxonomy.
"""

from __future__ import annotations

from chartnexus.shared_kernel.domain.errors import UpstreamError, ValidationError


class ChannelCredentialsInvalidError(ValidationError):
    """The supplied channel credentials are malformed (bad token shape, etc.)."""

    code = "channel_credentials_invalid"

    def __init__(self, message: str) -> None:
        super().__init__(message, field="token")


class ChannelNotConfiguredError(ValidationError):
    """An operation needs a connected channel, but none is configured/saved yet."""

    code = "channel_not_configured"


class ChannelVerificationError(ValidationError):
    """The provider rejected the credentials, or no chat could be resolved.

    User-fixable (wrong token, or they never messaged the bot), so it surfaces as
    a 422 with a clear message rather than a 500.
    """

    code = "channel_verification_failed"


class MessageSendError(UpstreamError):
    """A message could not be delivered to the channel."""

    code = "message_send_failed"

    def __init__(self, message: str, provider: str = "messaging") -> None:
        super().__init__(provider, message)
