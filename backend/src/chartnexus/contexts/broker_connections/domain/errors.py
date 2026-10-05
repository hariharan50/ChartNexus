"""Broker connection errors.

Each carries a code the UI switches on to choose the next step — re-enter keys,
reconnect, or wait — without parsing prose.
"""

from __future__ import annotations

from chartnexus.shared_kernel.domain.errors import (
    ConflictError,
    NotFoundError,
    UpstreamError,
    ValidationError,
)


class CredentialsMissingError(ConflictError):
    """No API application has been configured for this tenant yet."""

    code = "broker_credentials_missing"

    def __init__(self) -> None:
        super().__init__("Add your broker API credentials before connecting.")


class ConnectionNotFoundError(NotFoundError):
    code = "broker_not_connected"

    def __init__(self) -> None:
        super().__init__("broker connection")


class NotConnectedError(ConflictError):
    """Credentials exist but no usable token does."""

    code = "broker_not_connected"

    def __init__(self) -> None:
        super().__init__("Connect your broker account to load market data.")


class ConnectionExpiredError(ConflictError):
    """The broker rejected a token we hold.

    Distinct from "not connected": the user has connected before and only needs
    to re-authorise, which is a one-click action rather than re-entering keys.
    """

    code = "broker_connection_expired"

    def __init__(self) -> None:
        super().__init__("Your broker session expired. Reconnect to continue.")


class OAuthStateError(ValidationError):
    """The callback did not match a pending connection attempt.

    Covers unknown, expired, replayed, and tampered states — all of which mean
    the same thing to the user and must not be distinguished for an attacker.
    """

    code = "broker_state_invalid"

    def __init__(self) -> None:
        super().__init__("This connection link expired. Start again.")


class BrokerRejectedError(UpstreamError):
    """The broker refused the exchange or the request."""

    code = "broker_rejected"

    def __init__(self, message: str, *, broker: str = "fyers") -> None:
        super().__init__(broker, message)


class BrokerUnavailableError(UpstreamError):
    """The broker could not be reached, or timed out."""

    code = "broker_unavailable"

    def __init__(self, broker: str = "fyers") -> None:
        super().__init__(broker, "The broker is not responding. Try again shortly.")


class AlreadyConnectedError(ConflictError):
    code = "broker_already_connected"

    def __init__(self) -> None:
        super().__init__("This broker is already connected. Disconnect first.")
