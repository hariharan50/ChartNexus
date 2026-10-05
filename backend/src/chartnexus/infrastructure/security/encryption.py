"""Authenticated encryption for credentials held on behalf of a tenant.

Broker access tokens and API secrets are the one class of data here that is
useless to us in hashed form — we have to send the original value to the broker.
So they are encrypted at rest with AES-256-GCM, and a database dump on its own
yields nothing.

GCM gives us three things:

* a 256-bit key;
* one pass for confidentiality and integrity, with the tag verified before any
  plaintext is released;
* **associated data** — the property this design actually leans on. Every
  ciphertext is bound to the row and column it belongs to, so an attacker who
  can write to the database cannot move a token between tenants or between the
  access-token and refresh-token columns.

Ciphertext envelope::

    mcv1.<kid>.<base64url(nonce || ciphertext || tag)>

``kid`` names the key that encrypted the value, so rotation does not degrade
into trial decryption, and it is derived under its own HKDF label rather than
hashed from the key — it identifies a key without being a verifier for one.

The key is derived from ``CN_SECURITY_ENCRYPTION_KEY`` with HKDF rather than
used directly, so the setting can be any sufficiently long string instead of raw
key material. Deriving per purpose also means the token key and any future key
(say, for webhook secrets) are different values from one configured secret.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from chartnexus.shared_kernel.domain.errors import ChartNexusError

_MIN_SECRET_BYTES = 32
_KEY_BYTES = 32  # AES-256
_KID_BYTES = 6  # 8 base64url characters
_NONCE_BYTES = 12  # the size GCM is defined for; anything else costs a hash
_SCHEME = "mcv1"
_ENVELOPE_PARTS = 3  # scheme.kid.payload


class DecryptionError(ChartNexusError):
    """Ciphertext could not be decrypted or failed authentication.

    Raised for a changed key, a tampered value, and a ciphertext presented in
    the wrong place alike. Deliberately carries no detail beyond the purpose —
    an attacker who can read error messages must not learn which of those it
    was, because that distinction is an oracle.
    """

    code = "decryption_failed"

    def __init__(self, purpose: str) -> None:
        super().__init__(
            "Stored credentials could not be decrypted. The encryption key may have changed.",
            purpose=purpose,
        )


@dataclass(frozen=True, slots=True)
class _Key:
    """One derived AES-256 key and the identifier that names it."""

    kid: str
    aesgcm: AESGCM


@dataclass(slots=True)
class AesGcmCipher:
    """Implements the ``TokenCipher`` port.

    ``purpose`` binds the derived key to a use, so ciphertext from one context
    cannot be decrypted by another even though both come from the same
    configured secret.
    """

    keys: tuple[_Key, ...]
    purpose: str

    @classmethod
    def derive(
        cls,
        secret: str,
        *,
        purpose: str = "broker-credentials",
        previous_secrets: tuple[str, ...] = (),
    ) -> AesGcmCipher:
        """Build a cipher from a configured secret.

        ``previous_secrets`` supports key rotation: values are decrypted with
        any listed key but always re-encrypted with the first.
        """
        for value in (secret, *previous_secrets):
            if len(value.encode("utf-8")) < _MIN_SECRET_BYTES:
                msg = (
                    f"the encryption secret must be at least {_MIN_SECRET_BYTES} bytes; "
                    'generate one with: python -c "import secrets; '
                    'print(secrets.token_urlsafe(48))"'
                )
                raise ValueError(msg)

        keys = tuple(_derive_key(value, purpose) for value in (secret, *previous_secrets))
        return cls(keys=keys, purpose=purpose)

    @property
    def key_id(self) -> str:
        """Identifier of the key new ciphertext is written under."""
        return self.keys[0].kid

    def encrypt(self, plaintext: str, *, aad: str | None = None) -> str:
        """Encrypt under the primary key.

        ``aad`` is authenticated but not encrypted, and must be supplied
        identically to :meth:`decrypt`. Callers pass the location the value
        belongs to, which is what makes a relocated ciphertext unreadable.
        """
        key = self.keys[0]
        nonce = os.urandom(_NONCE_BYTES)
        sealed = key.aesgcm.encrypt(nonce, plaintext.encode("utf-8"), _aad_bytes(self.purpose, aad))
        return f"{_SCHEME}.{key.kid}.{_b64encode(nonce + sealed)}"

    def decrypt(self, ciphertext: str, *, aad: str | None = None) -> str:
        kid, payload = self._parse(ciphertext)
        associated = _aad_bytes(self.purpose, aad)
        nonce, sealed = payload[:_NONCE_BYTES], payload[_NONCE_BYTES:]
        for key in self._candidates(kid):
            try:
                return key.aesgcm.decrypt(nonce, sealed, associated).decode("utf-8")
            except (InvalidTag, ValueError):
                continue
        raise DecryptionError(self.purpose)

    def rotate(self, ciphertext: str, *, aad: str | None = None) -> str:
        """Re-encrypt under the current primary key."""
        return self.encrypt(self.decrypt(ciphertext, aad=aad), aad=aad)

    def needs_rotation(self, ciphertext: str) -> bool:
        """True when the value is not already GCM under the primary key."""
        kid, _ = self._parse(ciphertext)
        return kid != self.key_id

    # -- internals ----------------------------------------------------------

    def _parse(self, ciphertext: str) -> tuple[str, bytes]:
        """Split an envelope into key id and raw payload."""
        parts = ciphertext.split(".", 2)
        if len(parts) != _ENVELOPE_PARTS or parts[0] != _SCHEME:
            raise DecryptionError(self.purpose)

        _, kid, body = parts
        try:
            payload = _b64decode(body)
        except (ValueError, TypeError) as exc:
            raise DecryptionError(self.purpose) from exc

        if len(payload) <= _NONCE_BYTES:
            raise DecryptionError(self.purpose)
        return kid, payload

    def _candidates(self, kid: str) -> tuple[_Key, ...]:
        """Keys worth trying for a given key id.

        Normally exactly one. An unrecognised id falls back to trying them all,
        so a value written before key ids existed — or under a secret since
        re-derived — is still recoverable rather than silently lost.
        """
        matched = tuple(key for key in self.keys if key.kid == kid)
        return matched or self.keys


def _aad_bytes(purpose: str, aad: str | None) -> bytes:
    """Namespace the associated data.

    The purpose is folded in so the same context string under two purposes
    still yields distinct authenticated data, and the scheme version is folded
    in so a future envelope format cannot be confused with this one.
    """
    return f"{_SCHEME}:{purpose}:{aad or ''}".encode()


def _derive_key(secret: str, purpose: str) -> _Key:
    """HKDF-SHA256 to an AES-256 key plus a non-secret identifier for it.

    No salt: the input is a high-entropy configured secret rather than a
    password, and a random salt would have to be stored alongside every
    ciphertext to be reproducible.

    The key id comes from its own ``info`` label rather than from the key, so
    publishing it in every ciphertext does not hand out a value that can be
    checked against a guessed secret.
    """
    material = _hkdf(secret, f"chartnexus:{purpose}:aes256gcm:key", _KEY_BYTES)
    kid = _hkdf(secret, f"chartnexus:{purpose}:aes256gcm:kid", _KID_BYTES)
    return _Key(kid=_b64encode(kid), aesgcm=AESGCM(material))


def _hkdf(secret: str, info: str, length: int) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=None,
        info=info.encode(),
    ).derive(secret.encode("utf-8"))


def _b64encode(raw: bytes) -> str:
    """Unpadded urlsafe base64 — no ``=`` to survive a URL or a log line."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def mask(value: str, *, keep: int = 4) -> str:
    """Render a secret safe to log or return.

    Shows only enough to recognise which credential is configured.
    """
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * 6}{value[-keep:]}"
