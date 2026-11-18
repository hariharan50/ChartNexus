"""Value objects for broker connections."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from chartnexus.shared_kernel.domain.errors import ValidationError

# FYERS issues app ids in the form ABCDE123XY-100. Validated before we build an
# authorization URL, so a typo fails here with a clear message rather than as an
# opaque rejection on the broker's consent screen.
_FYERS_APP_ID = re.compile(r"^[A-Z0-9]{4,20}-[0-9]{2,4}$")

# Kite Connect API keys and secrets are lower-case alphanumeric strings issued
# by developers.kite.trade. The bounds are deliberately loose: Zerodha does not
# publish exact lengths, and refusing a real key is worse than letting a typo
# reach the login page, where Zerodha rejects it with its own message.
_KITE_API_KEY = re.compile(r"^[a-z0-9]{6,32}$")
_KITE_API_SECRET = re.compile(r"^[a-z0-9]{16,64}$")

# The broker *login* id the user means to connect as — FYERS "XA12345",
# Zerodha "AB1234". Not secret: it is printed on every contract note.
_CLIENT_ID = re.compile(r"^[A-Z][A-Z0-9]{3,9}$")

# A masked Kite key keeps its first four and last two characters.
_KITE_MASK_VISIBLE = 6

_MIN_SECRET_LENGTH = 5
_MAX_SECRET_LENGTH = 64


class BrokerName(StrEnum):
    FYERS = "fyers"
    KITE = "kite"

    @property
    def label(self) -> str:
        """How the broker is named to a person."""
        return "Zerodha Kite" if self is BrokerName.KITE else "FYERS"


class ConnectionStatus(StrEnum):
    PENDING = "pending"
    """Credentials saved, OAuth not completed."""

    ACTIVE = "active"
    """Holds a token the broker accepted."""

    EXPIRED = "expired"
    """Held a token; the broker has since rejected it, or it ran out."""

    REVOKED = "revoked"
    """Deliberately ended by the tenant."""

    @property
    def can_serve_data(self) -> bool:
        return self is ConnectionStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class BrokerCredentials:
    """A tenant's own broker API application.

    ``app_id`` is the broker's public application identifier — the FYERS App
    ID, or the Kite API key. It travels in the authorization URL and is not
    secret. ``secret`` is, and never leaves the server after it is stored.

    Construct through :meth:`parse` so the rules for the right broker apply.
    Direct construction validates against the broker it is told about, which
    defaults to FYERS for every caller that predates Kite.
    """

    app_id: str
    secret: str
    broker: BrokerName = BrokerName.FYERS

    def __post_init__(self) -> None:
        if self.broker is BrokerName.KITE:
            _validate_kite(self.app_id, self.secret)
        else:
            _validate_fyers(self.app_id, self.secret)

    @classmethod
    def parse(
        cls, app_id: str, secret: str, broker: BrokerName = BrokerName.FYERS
    ) -> BrokerCredentials:
        """Normalise then validate, per broker.

        FYERS app ids are upper-case; Kite keys are lower-case. Each is folded
        to its own case so a pasted value with the wrong case still works.
        """
        raw_id = (app_id or "").strip()
        normalised = raw_id.lower() if broker is BrokerName.KITE else raw_id.upper()
        return cls(app_id=normalised, secret=(secret or "").strip(), broker=broker)

    @property
    def masked_app_id(self) -> str:
        """Enough to recognise which application is configured, and no more."""
        if self.broker is BrokerName.KITE:
            key = self.app_id
            if len(key) <= _KITE_MASK_VISIBLE:
                return key
            return f"{key[:4]}{'*' * (len(key) - _KITE_MASK_VISIBLE)}{key[-2:]}"
        # The suffix after the dash identifies the app; the prefix is the part
        # worth obscuring.
        head, _, tail = self.app_id.partition("-")
        visible = head[:4]
        return f"{visible}{'*' * max(0, len(head) - 4)}-{tail}" if tail else visible

    def __repr__(self) -> str:
        return (
            f"BrokerCredentials(broker={self.broker.value!r}, app_id={self.app_id!r}, secret=***)"
        )


def _validate_fyers(app_id: str, secret: str) -> None:
    if not _FYERS_APP_ID.match(app_id):
        raise ValidationError("App ID must look like ABCDE123XY-100.", field="app_id")

    length = len(secret)
    if not (_MIN_SECRET_LENGTH <= length <= _MAX_SECRET_LENGTH):
        raise ValidationError(
            f"Secret ID must be between {_MIN_SECRET_LENGTH} and {_MAX_SECRET_LENGTH} characters.",
            field="secret",
        )
    if any(character in secret for character in "\r\n"):
        raise ValidationError("Secret ID must not contain line breaks.", field="secret")
    if not secret.isprintable():
        raise ValidationError("Secret ID contains unsupported characters.", field="secret")


def _validate_kite(api_key: str, api_secret: str) -> None:
    if not _KITE_API_KEY.match(api_key):
        raise ValidationError(
            "API key must be the lower-case letters and digits shown on developers.kite.trade.",
            field="app_id",
        )
    if not _KITE_API_SECRET.match(api_secret):
        raise ValidationError(
            "API secret must be the lower-case letters and digits shown on developers.kite.trade.",
            field="secret",
        )


def parse_client_id(value: str | None) -> str | None:
    """Normalise an optional broker login id, or refuse a malformed one.

    Empty means "don't check which account logs in" and is allowed.
    """
    text = (value or "").strip().upper()
    if not text:
        return None
    if not _CLIENT_ID.match(text):
        raise ValidationError(
            "Client ID must be your broker login ID, for example AB1234.",
            field="client_id",
        )
    return text


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
