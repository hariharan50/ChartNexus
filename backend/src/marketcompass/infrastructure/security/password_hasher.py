"""Argon2id password hashing.

Argon2id is the current OWASP recommendation: memory-hard, so GPU and ASIC
attacks lose most of their advantage. Parameters come from settings and can be
raised over time — :meth:`needs_rehash` then upgrades each hash on the next
successful login.
"""

from __future__ import annotations

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import HashingError, InvalidHashError, VerificationError, VerifyMismatchError

from marketcompass.bootstrap.settings import SecuritySettings

# Verified once at import so the timing-equalising path costs the same as a real
# verification without hashing a throwaway password on every miss.
_DUMMY_PASSWORD = "mc-dummy-password-for-constant-time-verification"  # noqa: S105


class Argon2Hasher:
    """Implements the ``PasswordHasher`` port."""

    def __init__(self, settings: SecuritySettings) -> None:
        self._hasher = Argon2PasswordHasher(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_cost_kib,
            parallelism=settings.argon2_parallelism,
            hash_len=32,
            salt_len=16,
        )
        self._dummy_hash = self._hasher.hash(_DUMMY_PASSWORD)

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except (InvalidHashError, HashingError):
            # An unparsable hash can never be verified, so force a rehash the
            # next time the plaintext is available.
            return True

    def dummy_verify(self) -> None:
        """Spend a verification's worth of CPU against a fixed hash."""
        try:
            self._hasher.verify(self._dummy_hash, "not-the-dummy-password")
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return
