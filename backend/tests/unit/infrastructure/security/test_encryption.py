"""AES-256-GCM credential encryption.

Every broker secret in the database rests on this module, so the tests cover
the properties an attacker would probe: that a wrong key fails, that a modified
ciphertext fails rather than decrypting to garbage, and that a ciphertext moved
to a different row or column fails too.
"""

from __future__ import annotations

import base64

import pytest

from chartnexus.infrastructure.security.encryption import (
    AesGcmCipher,
    DecryptionError,
    mask,
)

pytestmark = pytest.mark.unit

SECRET = "a-secret-long-enough-to-derive-a-key-from"
OTHER_SECRET = "a-completely-different-secret-of-length"


def _cipher(
    secret: str = SECRET,
    *,
    purpose: str = "broker-credentials",
    previous_secrets: tuple[str, ...] = (),
) -> AesGcmCipher:
    return AesGcmCipher.derive(secret, purpose=purpose, previous_secrets=previous_secrets)


# --- round trip ------------------------------------------------------------


def test_cipher_round_trips() -> None:
    cipher = _cipher()
    assert cipher.decrypt(cipher.encrypt("token-value")) == "token-value"


def test_round_trips_with_associated_data() -> None:
    cipher = _cipher()
    sealed = cipher.encrypt("token-value", aad="tenant-a:fyers:access_token")
    assert cipher.decrypt(sealed, aad="tenant-a:fyers:access_token") == "token-value"


def test_round_trips_non_ascii_and_empty_plaintext() -> None:
    cipher = _cipher()
    for plaintext in ("", "ünïcode-tøken", "x" * 4096):
        assert cipher.decrypt(cipher.encrypt(plaintext)) == plaintext


def test_ciphertext_does_not_contain_the_plaintext() -> None:
    assert "token-value" not in _cipher().encrypt("token-value")


def test_encryption_is_non_deterministic() -> None:
    """A fresh nonce per message: identical plaintexts must not collide."""
    cipher = _cipher()
    assert cipher.encrypt("same") != cipher.encrypt("same")


def test_nonces_do_not_repeat_across_many_encryptions() -> None:
    cipher = _cipher()
    envelopes = {cipher.encrypt("same") for _ in range(500)}
    assert len(envelopes) == 500


# --- envelope --------------------------------------------------------------


def test_envelope_is_versioned_and_names_its_key() -> None:
    cipher = _cipher()
    scheme, kid, body = cipher.encrypt("token-value").split(".")

    assert scheme == "mcv1"
    assert kid == cipher.key_id
    assert "=" not in body, "padding would break anything that treats this as a token"


def test_envelope_carries_a_nonce_and_a_tag() -> None:
    """12-byte nonce + 16-byte tag on top of the plaintext length."""
    _, _, body = _cipher().encrypt("abcd").split(".")
    payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))

    assert len(payload) == 12 + len("abcd") + 16


def test_key_id_is_stable_for_a_secret_and_differs_between_secrets() -> None:
    assert _cipher().key_id == _cipher().key_id
    assert _cipher().key_id != _cipher(OTHER_SECRET).key_id


def test_key_id_is_not_derived_from_the_key_itself() -> None:
    """The id travels in plaintext, so it must not verify a guessed secret."""
    _, kid, body = _cipher().encrypt("v").split(".")
    payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))

    assert base64.urlsafe_b64decode(kid + "==") not in payload


# --- the properties that matter --------------------------------------------


def test_a_different_key_cannot_decrypt() -> None:
    ciphertext = _cipher().encrypt("token-value")

    with pytest.raises(DecryptionError):
        _cipher(OTHER_SECRET).decrypt(ciphertext)


def test_a_different_purpose_cannot_decrypt() -> None:
    """Key separation: one configured secret, distinct keys per use."""
    ciphertext = _cipher(purpose="broker-credentials").encrypt("v")

    with pytest.raises(DecryptionError):
        _cipher(purpose="webhook-secrets").decrypt(ciphertext)


def test_tampering_with_the_ciphertext_is_detected() -> None:
    """GCM authenticates: a flipped bit fails loudly, not silently."""
    cipher = _cipher()
    scheme, kid, body = cipher.encrypt("token-value").split(".")
    payload = bytearray(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload[-1] ^= 0x01
    tampered = base64.urlsafe_b64encode(bytes(payload)).decode().rstrip("=")

    with pytest.raises(DecryptionError):
        cipher.decrypt(f"{scheme}.{kid}.{tampered}")


def test_tampering_with_the_nonce_is_detected() -> None:
    cipher = _cipher()
    scheme, kid, body = cipher.encrypt("token-value").split(".")
    payload = bytearray(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload[0] ^= 0x01
    tampered = base64.urlsafe_b64encode(bytes(payload)).decode().rstrip("=")

    with pytest.raises(DecryptionError):
        cipher.decrypt(f"{scheme}.{kid}.{tampered}")


def test_associated_data_must_match() -> None:
    """The point of AAD: a value lifted into another row will not decrypt."""
    cipher = _cipher()
    sealed = cipher.encrypt("token-value", aad="tenant-a:fyers:access_token")

    with pytest.raises(DecryptionError):
        cipher.decrypt(sealed, aad="tenant-b:fyers:access_token")


def test_associated_data_cannot_be_dropped() -> None:
    cipher = _cipher()
    sealed = cipher.encrypt("token-value", aad="tenant-a:fyers:access_token")

    with pytest.raises(DecryptionError):
        cipher.decrypt(sealed)


def test_associated_data_cannot_be_added() -> None:
    cipher = _cipher()
    sealed = cipher.encrypt("token-value")

    with pytest.raises(DecryptionError):
        cipher.decrypt(sealed, aad="tenant-a:fyers:access_token")


# --- rotation --------------------------------------------------------------


def test_rotation_decrypts_with_the_previous_key() -> None:
    ciphertext = _cipher().encrypt("token-value")
    rotated = _cipher("a-brand-new-secret-of-sufficient-length", previous_secrets=(SECRET,))

    assert rotated.decrypt(ciphertext) == "token-value"


def test_rotation_preserves_associated_data() -> None:
    aad = "tenant-a:fyers:access_token"
    ciphertext = _cipher().encrypt("token-value", aad=aad)
    rotated = _cipher("a-brand-new-secret-of-sufficient-length", previous_secrets=(SECRET,))

    assert rotated.decrypt(ciphertext, aad=aad) == "token-value"


def test_rotate_re_encrypts_under_the_primary_key() -> None:
    old = _cipher()
    ciphertext = old.encrypt("token-value")
    new = _cipher("a-brand-new-secret-of-sufficient-length", previous_secrets=(SECRET,))

    upgraded = new.rotate(ciphertext)

    assert upgraded.split(".")[1] == new.key_id
    assert new.decrypt(upgraded) == "token-value"
    with pytest.raises(DecryptionError):
        old.decrypt(upgraded)


def test_needs_rotation_flags_only_stale_ciphertext() -> None:
    old = _cipher()
    stale = old.encrypt("token-value")
    new = _cipher("a-brand-new-secret-of-sufficient-length", previous_secrets=(SECRET,))

    assert new.needs_rotation(stale)
    assert not new.needs_rotation(new.encrypt("token-value"))


# --- misuse ----------------------------------------------------------------


def test_a_short_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        _cipher("too-short")


def test_a_short_retired_secret_is_refused() -> None:
    """A retired key is still key material; the same floor applies."""
    with pytest.raises(ValueError, match="at least 32 bytes"):
        _cipher(SECRET, previous_secrets=("too-short",))


@pytest.mark.parametrize(
    "value",
    [
        "not-ciphertext",
        "mcv1.badkid.not-base64!!",
        "mcv1.badkid",  # no payload
        "mcv1..",
        "mcv9.somekid.YWJjZA",  # a scheme this build does not know
        # A pre-GCM Fernet value. That format is gone, and a row still holding
        # one must fail rather than be interpreted: the repository reports the
        # credential as absent and the user reconnects.
        "gAAAAABn0000000000000000000000000000000000000000000000",
        "",
    ],
)
def test_garbage_ciphertext_fails_cleanly(value: str) -> None:
    with pytest.raises(DecryptionError):
        _cipher().decrypt(value)


def test_a_truncated_payload_fails_cleanly() -> None:
    """Shorter than a nonce: must not slice into a negative-length read."""
    with pytest.raises(DecryptionError):
        _cipher().decrypt("mcv1.somekid.YWJj")


def test_the_error_reveals_nothing_about_the_failure() -> None:
    """Wrong key and wrong AAD must be indistinguishable to a caller."""
    cipher = _cipher()
    wrong_key = _cipher(OTHER_SECRET).encrypt("token-value")
    wrong_aad = cipher.encrypt("token-value", aad="tenant-a")

    with pytest.raises(DecryptionError) as first:
        cipher.decrypt(wrong_key)
    with pytest.raises(DecryptionError) as second:
        cipher.decrypt(wrong_aad, aad="tenant-b")

    assert str(first.value) == str(second.value)
    assert "token-value" not in str(first.value)


# --- masking ---------------------------------------------------------------


def test_mask_keeps_only_the_edges() -> None:
    assert mask("ABCDEFGHIJKL") == "ABCD******IJKL"
    assert "SECRET" not in mask("SECRET")
