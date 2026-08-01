"""Value objects for the identity context."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from marketcompass.shared_kernel.domain.errors import ValidationError

# Deliberately permissive: RFC 5322 in full accepts addresses no provider will
# deliver to, and over-strict patterns reject valid ones. Deliverability is
# proven by the verification email, not by this regex.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")
_MAX_EMAIL_LENGTH = 254
_MAX_PASSWORD_LENGTH = 1024


@dataclass(frozen=True, slots=True)
class EmailAddress:
    """A normalised email address.

    Normalisation matters for security, not tidiness: ``User@x.com`` and
    ``user@x.com`` must resolve to one account, or an attacker can register a
    case variant of somebody else's address.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValidationError("email address is required")
        if len(self.value) > _MAX_EMAIL_LENGTH:
            raise ValidationError("email address is too long")
        if not _EMAIL_PATTERN.match(self.value):
            raise ValidationError("email address is not valid")

    @classmethod
    def parse(cls, raw: str) -> EmailAddress:
        normalised = unicodedata.normalize("NFKC", (raw or "").strip()).lower()
        return cls(normalised)

    @property
    def domain(self) -> str:
        return self.value.rsplit("@", 1)[1]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class RawPassword:
    """A password as typed by the user. Never logged, never persisted."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValidationError("password is required")
        # Argon2 costs scale with input length; an unbounded password is a
        # cheap way to burn CPU on the login endpoint.
        if len(self.value.encode("utf-8")) > _MAX_PASSWORD_LENGTH:
            raise ValidationError("password is too long")

    def __repr__(self) -> str:
        return "RawPassword(***)"

    def __str__(self) -> str:
        return "***"


class UserStatus(StrEnum):
    ACTIVE = "active"
    PENDING_VERIFICATION = "pending_verification"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"

    @property
    def can_authenticate(self) -> bool:
        return self is UserStatus.ACTIVE


class Role(StrEnum):
    """Coarse role. Fine-grained permissions live in the entitlements context."""

    OWNER = "owner"
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class AuthProvider(StrEnum):
    PASSWORD = "password"  # noqa: S105 — provider name
    GOOGLE = "google"
