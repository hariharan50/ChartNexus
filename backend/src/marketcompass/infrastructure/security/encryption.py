"""Envelope encryption for credentials held on behalf of a tenant.

Broker access tokens and API secrets are the one class of data here that is
useless to us in hashed form — we have to send the original value to the broker.
So they are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256), and a
database dump on its own yields nothing.

The key is derived from ``MC_SECURITY_ENCRYPTION_KEY`` with HKDF rather than
used directly, so the setting can be any sufficiently long string instead of a
base64 Fernet key. Deriving per purpose also means the token key and any future
key (say, for webhook secrets) are different values from one configured secret.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from marketcompass.shared_kernel.domain.errors import MarketCompassError

_MIN_SECRET_BYTES = 32
_KEY_BYTES = 32


class DecryptionError(MarketCompassError):
    """Ciphertext could not be decrypted.

    Almost always means the encryption key changed. Deliberately carries no
    detail about the ciphertext — an attacker who can read error messages must
    not learn anything from a failed attempt.
    """

    code = "decryption_failed"

    def __init__(self, purpose: str) -> None:
        super().__init__(
            "Stored credentials could not be decrypted. The encryption key may have changed.",
            purpose=purpose,
        )


@dataclass(slots=True)
class FernetCipher:
    """Implements the ``TokenCipher`` port.

    ``purpose`` binds the derived key to a use, so ciphertext from one context
    cannot be decrypted by another even though both come from the same
    configured secret.
    """

    fernet: MultiFernet
    purpose: str

    @classmethod
    def derive(
        cls,
        secret: str,
        *,
        purpose: str = "broker-credentials",
        previous_secrets: tuple[str, ...] = (),
    ) -> FernetCipher:
        """Build a cipher from a configured secret.

        ``previous_secrets`` supports key rotation: values are decrypted with
        any listed key but always re-encrypted with the first.
        """
        if len(secret.encode("utf-8")) < _MIN_SECRET_BYTES:
            msg = (
                f"the encryption secret must be at least {_MIN_SECRET_BYTES} bytes; "
                'generate one with: python -c "import secrets; '
                'print(secrets.token_urlsafe(48))"'
            )
            raise ValueError(msg)

        keys = [Fernet(_derive_key(value, purpose)) for value in (secret, *previous_secrets)]
        return cls(fernet=MultiFernet(keys), purpose=purpose)

    def encrypt(self, plaintext: str) -> str:
        return self.fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self.fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError) as exc:
            raise DecryptionError(self.purpose) from exc

    def rotate(self, ciphertext: str) -> str:
        """Re-encrypt under the current primary key."""
        try:
            return self.fernet.rotate(ciphertext.encode("ascii")).decode("ascii")
        except (InvalidToken, ValueError, TypeError) as exc:
            raise DecryptionError(self.purpose) from exc


def _derive_key(secret: str, purpose: str) -> bytes:
    """HKDF-SHA256 to a urlsafe-base64 32-byte key, as Fernet expects.

    No salt: the input is a high-entropy configured secret rather than a
    password, and a random salt would have to be stored alongside every
    ciphertext to be reproducible.
    """
    raw = HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_BYTES,
        salt=None,
        info=f"marketcompass:{purpose}".encode(),
    ).derive(secret.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def mask(value: str, *, keep: int = 4) -> str:
    """Render a secret safe to log or return.

    Shows only enough to recognise which credential is configured.
    """
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * 6}{value[-keep:]}"
