"""Value objects for broker connections."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from chartnexus.shared_kernel.domain.errors import ValidationError

# FYERS issues app ids in the form ABCDE123XY-100. Validated before we build an
# authorization URL, so a typo fails here with a clear message rather than as an
# opaque rejection on the broker's consent screen.
_APP_ID_PATTERN = re.compile(r"^[A-Z0-9]{4,20}-[0-9]{2,4}$")

_MIN_SECRET_LENGTH = 5
_MAX_SECRET_LENGTH = 64


class BrokerName(StrEnum):
    FYERS = "fyers"


class ConnectionStatus(StrEnum):
    PENDING = "pending"
    """Credentials saved, OAuth not completed."""

    ACTIVE = "active"
    """Holds a token the broker accepted."""

    EXPIRED = "expired"
    """Held a token; the broker has since rejected it."""

    REVOKED = "revoked"
    """Deliberately ended by the tenant."""

    @property
    def can_serve_data(self) -> bool:
        return self is ConnectionStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class BrokerCredentials:
    """A tenant's own broker API application.

    The app id is not secret — it travels in the authorization URL. The secret
    is, and never leaves the server after it is stored.
    """

    app_id: str
    secret: str

    def __post_init__(self) -> None:
        if not _APP_ID_PATTERN.match(self.app_id):
            raise ValidationError("App ID must look like ABCDE123XY-100.", field="app_id")

        length = len(self.secret)
        if not (_MIN_SECRET_LENGTH <= length <= _MAX_SECRET_LENGTH):
            raise ValidationError(
                f"Secret ID must be between {_MIN_SECRET_LENGTH} and "
                f"{_MAX_SECRET_LENGTH} characters.",
                field="secret",
            )
        if any(character in self.secret for character in "\r\n"):
            raise ValidationError("Secret ID must not contain line breaks.", field="secret")
        if not self.secret.isprintable():
            raise ValidationError("Secret ID contains unsupported characters.", field="secret")

    @classmethod
    def parse(cls, app_id: str, secret: str) -> BrokerCredentials:
        """Normalise then validate. Broker app ids are upper-case."""
        return cls(app_id=(app_id or "").strip().upper(), secret=(secret or "").strip())

    def __repr__(self) -> str:
        return f"BrokerCredentials(app_id={self.app_id!r}, secret=***)"


@dataclass(frozen=True, slots=True)
class BrokerProfile:
    """The subset of the broker's account profile worth showing a user."""

    broker_user_id: str
    display_name: str
    email: str | None = None

    def as_dict(self) -> dict[str, str]:
        data = {"broker_user_id": self.broker_user_id, "display_name": self.display_name}
        if self.email:
            data["email"] = self.email
        return data
