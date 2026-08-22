"""The AI-key ciphertext must be isolated by user and by purpose.

These pin the two properties the repository relies on: a key stored for one user
cannot decrypt under another user's row (the AAD binding), and an AI-settings
ciphertext cannot be read in the broker context even though both derive from the
same configured secret (the HKDF purpose split).
"""

from __future__ import annotations

import pytest

from marketcompass.infrastructure.security.encryption import AesGcmCipher, DecryptionError

pytestmark = pytest.mark.unit

SECRET = "a-secret-long-enough-to-derive-a-key-from"
KEY = "sk-ant-abcd1234efgh5678"


def _ai_cipher() -> AesGcmCipher:
    return AesGcmCipher.derive(SECRET, purpose="ai-settings")


def _aad(user: str) -> str:
    return f"ai_settings:{user}:anthropic:api_key"


def test_round_trips_under_the_user_aad() -> None:
    cipher = _ai_cipher()
    sealed = cipher.encrypt(KEY, aad=_aad("user-a"))
    assert cipher.decrypt(sealed, aad=_aad("user-a")) == KEY


def test_a_key_cannot_be_lifted_into_another_users_row() -> None:
    cipher = _ai_cipher()
    sealed = cipher.encrypt(KEY, aad=_aad("user-a"))
    with pytest.raises(DecryptionError):
        cipher.decrypt(sealed, aad=_aad("user-b"))


def test_ai_ciphertext_cannot_be_decrypted_in_the_broker_context() -> None:
    ai = _ai_cipher()
    broker = AesGcmCipher.derive(SECRET, purpose="broker-credentials")
    sealed = ai.encrypt(KEY, aad=_aad("user-a"))
    with pytest.raises(DecryptionError):
        broker.decrypt(sealed, aad=_aad("user-a"))
