"""Trade Buddy's own failure types.

Subclassed from the shared-kernel bases so the HTTP layer's existing exception
handlers map them to problem+json without this context knowing FastAPI exists.
``NotFoundError`` takes (resource, identifier) and ``UpstreamError`` takes
(provider, message) — both signatures are inherited as-is.
"""

from __future__ import annotations

from chartnexus.shared_kernel.domain.errors import (
    NotFoundError,
    UpstreamError,
    ValidationError,
)


class NoLevelsMarkedError(NotFoundError):
    """A test alert or a watch was requested before any level was marked."""

    def __init__(self, symbol: str) -> None:
        super().__init__("marked levels", symbol)
        self.symbol = symbol


class AlertDeliveryError(UpstreamError):
    """Every channel a policy allowed refused the message.

    Distinct from a single channel failing: the router degrades to Telegram-only
    when the WhatsApp budget is spent, and that is a success, not an error. This
    is the case where nothing got through at all — which the caller must be able
    to tell apart from a delivered alert.
    """

    def __init__(self, detail: str) -> None:
        super().__init__("notifications", f"Alert delivery failed on every channel: {detail}")


class ChannelVerificationError(ValidationError):
    """The provider refused the credentials, or could not be reached to ask.

    Separate from a send failure: this one is answered by fixing the token,
    the other by retrying.
    """

    def __init__(self, detail: str, *, provider: str) -> None:
        super().__init__(f"{provider} rejected the credentials: {detail}")
        self.provider = provider


class ChannelNotReadyError(ValidationError):
    """A send was asked for on a channel that cannot deliver yet.

    Raised rather than silently dropped, because "no alert arrived" is the
    symptom this whole feature exists to make impossible to misread.
    """

    def __init__(self, channel: str) -> None:
        super().__init__(
            f"The {channel} channel is not ready. Connect a bot and link a chat first."
        )
        self.channel = channel
