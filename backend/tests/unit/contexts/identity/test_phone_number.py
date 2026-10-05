"""The PhoneNumber value object.

Normalisation is the whole point: a number is a sign-in identifier, so every
spelling of one number has to collapse to a single stored form or the same
person can register twice and sign in unpredictably.
"""

from __future__ import annotations

import pytest

from chartnexus.contexts.identity.domain.value_objects import PhoneNumber
from chartnexus.shared_kernel.domain.errors import ValidationError

pytestmark = pytest.mark.unit

E164 = "+919876543210"


@pytest.mark.parametrize(
    "typed",
    [
        "9876543210",  # bare national
        "+919876543210",  # already E.164
        "09876543210",  # trunk prefix
        "919876543210",  # country code, no plus
        "+91 98765 43210",  # spaced, as printed on a card
        "+91-98765-43210",  # hyphenated
        "(+91) 98765 43210",  # parenthesised
        "  9876543210  ",  # padded by a careless paste
    ],
)
def test_every_spelling_normalises_to_one_stored_form(typed: str) -> None:
    assert PhoneNumber.parse(typed).value == E164


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("", "empty"),
        ("   ", "whitespace only"),
        ("987654321", "nine digits"),
        ("98765432101", "eleven digits"),
        ("1234567890", "Indian mobiles never start with 1"),
        ("5876543210", "nor with 5"),
        ("+1 415 555 0132", "not an Indian number"),
        ("98765abcde", "letters"),
        ("+91", "country code only"),
    ],
)
def test_invalid_numbers_are_rejected(raw: str, reason: str) -> None:
    with pytest.raises(ValidationError):
        PhoneNumber.parse(raw)


def test_national_drops_the_country_code_for_display() -> None:
    assert PhoneNumber.parse(E164).national == "9876543210"


def test_the_bare_constructor_validates_but_does_not_normalise() -> None:
    """How rows are rehydrated: already normalised, so only checked.

    Passing an un-normalised value must fail rather than be quietly fixed —
    that would hide a bad write instead of surfacing it.
    """
    assert PhoneNumber(E164).value == E164
    with pytest.raises(ValidationError):
        PhoneNumber("9876543210")


def test_equality_is_by_value_so_lookups_match() -> None:
    assert PhoneNumber.parse("9876543210") == PhoneNumber.parse("+91 98765 43210")
