"""Password strength rules.

Length is the rule that actually matters, so the policy leads with it and adds
only checks that block genuinely weak choices. Composition rules ("must contain
a symbol") push users toward predictable substitutions, so they are not used.
"""

from __future__ import annotations

from dataclasses import dataclass

from marketcompass.contexts.identity.domain.value_objects import (
    EmailAddress,
    PhoneNumber,
    RawPassword,
)
from marketcompass.shared_kernel.domain.errors import ValidationError

# The passwords that show up first in every credential-stuffing list. A full
# breach-corpus check (k-anonymity against HIBP) belongs behind a port; this is
# the floor that works offline and in tests.
_COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password123",
        "123456",
        "12345678",
        "123456789",
        "qwerty",
        "qwertyuiop",
        "letmein",
        "welcome",
        "admin",
        "administrator",
        "iloveyou",
        "monkey",
        "dragon",
        "abc123",
        "trustno1",
        "changeme",
        "marketcompass",
    }
)


# Below this length a local part ("bob") matches too many innocent passwords.
_MIN_LOCAL_PART_FOR_SIMILARITY = 4


@dataclass(frozen=True, slots=True)
class PasswordPolicy:
    min_length: int = 12
    max_repeated_characters: int = 4

    def validate(
        self,
        password: RawPassword,
        *,
        email: EmailAddress | None = None,
        phone: PhoneNumber | None = None,
    ) -> None:
        """Raise :class:`ValidationError` if the password is unacceptable."""
        value = password.value

        if len(value) < self.min_length:
            raise ValidationError(
                f"password must be at least {self.min_length} characters",
                field="password",
            )

        folded = value.casefold()

        if folded in _COMMON_PASSWORDS:
            raise ValidationError("this password appears in public breach lists", field="password")

        if _longest_run(folded) > self.max_repeated_characters:
            raise ValidationError(
                "password must not repeat the same character that many times",
                field="password",
            )

        if email is not None and self._resembles_email(folded, email):
            raise ValidationError("password must not contain your email address", field="password")

        if phone is not None and phone.national in folded:
            raise ValidationError("password must not contain your phone number", field="password")

    @staticmethod
    def _resembles_email(folded_password: str, email: EmailAddress) -> bool:
        local_part = email.value.split("@", 1)[0]
        if (
            local_part
            and len(local_part) >= _MIN_LOCAL_PART_FOR_SIMILARITY
            and local_part in folded_password
        ):
            return True
        return email.value in folded_password


def _longest_run(value: str) -> int:
    longest = 0
    current = 0
    previous = ""
    for character in value:
        current = current + 1 if character == previous else 1
        longest = max(longest, current)
        previous = character
    return longest
