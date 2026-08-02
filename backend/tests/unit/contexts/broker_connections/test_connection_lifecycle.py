"""Credential validation, encryption, and the connect/disconnect/revoke rules."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from marketcompass.contexts.broker_connections.domain.connection import BrokerConnection
from marketcompass.contexts.broker_connections.domain.errors import (
    ConnectionExpiredError,
    CredentialsMissingError,
    NotConnectedError,
)
from marketcompass.contexts.broker_connections.domain.value_objects import (
    BrokerCredentials,
    BrokerName,
    BrokerProfile,
    ConnectionStatus,
)
from marketcompass.infrastructure.security.encryption import (
    DecryptionError,
    FernetCipher,
    mask,
)
from marketcompass.shared_kernel.domain.errors import ValidationError
from marketcompass.shared_kernel.types.identifiers import TenantId, new_id

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 1, 9, 30, tzinfo=UTC)
LATER = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
SECRET = "a-secret-long-enough-to-derive-a-key-from"


def _connection() -> BrokerConnection:
    return BrokerConnection.start(
        tenant_id=TenantId(new_id()),
        broker=BrokerName.FYERS,
        credentials=BrokerCredentials("ABCDE123XY-100", "app-secret-value"),
        now=NOW,
    )


# --- credentials -----------------------------------------------------------


@pytest.mark.parametrize("app_id", ["ABCDE123XY-100", "AB12-99", "ABCDEFGHIJKLMNOPQRST-1234"])
def test_valid_app_ids_are_accepted(app_id: str) -> None:
    BrokerCredentials(app_id, "some-secret")


@pytest.mark.parametrize(
    "app_id", ["nope", "ABC-1", "ABCDE123XY", "ABCDE123XY-", "abcde123xy-100!", ""]
)
def test_malformed_app_ids_are_rejected(app_id: str) -> None:
    with pytest.raises(ValidationError):
        BrokerCredentials(app_id, "some-secret")


def test_app_id_is_upper_cased_on_parse() -> None:
    assert BrokerCredentials.parse(" abcde123xy-100 ", " s3cret ").app_id == "ABCDE123XY-100"


@pytest.mark.parametrize("secret", ["shrt", "x" * 65, "has\nnewline", "has\rreturn"])
def test_unusable_secrets_are_rejected(secret: str) -> None:
    with pytest.raises(ValidationError):
        BrokerCredentials("ABCDE123XY-100", secret)


def test_secret_never_appears_in_a_repr() -> None:
    credentials = BrokerCredentials("ABCDE123XY-100", "super-secret-value")
    assert "super-secret-value" not in repr(credentials)


def test_app_id_is_masked_for_display() -> None:
    connection = _connection()
    masked = connection.masked_app_id
    assert masked is not None
    assert masked.endswith("-100")
    assert masked != "ABCDE123XY-100"


# --- encryption ------------------------------------------------------------


def test_cipher_round_trips() -> None:
    cipher = FernetCipher.derive(SECRET)
    assert cipher.decrypt(cipher.encrypt("token-value")) == "token-value"


def test_ciphertext_does_not_contain_the_plaintext() -> None:
    cipher = FernetCipher.derive(SECRET)
    assert "token-value" not in cipher.encrypt("token-value")


def test_encryption_is_non_deterministic() -> None:
    """Identical plaintexts must not produce identical ciphertexts."""
    cipher = FernetCipher.derive(SECRET)
    assert cipher.encrypt("same") != cipher.encrypt("same")


def test_a_different_key_cannot_decrypt() -> None:
    ciphertext = FernetCipher.derive(SECRET).encrypt("token-value")
    other = FernetCipher.derive("a-completely-different-secret-of-length")

    with pytest.raises(DecryptionError):
        other.decrypt(ciphertext)


def test_a_different_purpose_cannot_decrypt() -> None:
    """Key separation: one configured secret, distinct keys per use."""
    ciphertext = FernetCipher.derive(SECRET, purpose="broker-credentials").encrypt("v")
    other = FernetCipher.derive(SECRET, purpose="webhook-secrets")

    with pytest.raises(DecryptionError):
        other.decrypt(ciphertext)


def test_rotation_decrypts_with_the_previous_key() -> None:
    old = FernetCipher.derive(SECRET)
    ciphertext = old.encrypt("token-value")
    rotated = FernetCipher.derive(
        "a-brand-new-secret-of-sufficient-length", previous_secrets=(SECRET,)
    )

    assert rotated.decrypt(ciphertext) == "token-value"


def test_a_short_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        FernetCipher.derive("too-short")


def test_garbage_ciphertext_fails_cleanly() -> None:
    with pytest.raises(DecryptionError):
        FernetCipher.derive(SECRET).decrypt("not-ciphertext")


def test_mask_keeps_only_the_edges() -> None:
    assert mask("ABCDEFGHIJKL") == "ABCD******IJKL"
    assert "SECRET" not in mask("SECRET")


# --- lifecycle -------------------------------------------------------------


def test_a_new_connection_is_pending_and_has_no_token() -> None:
    connection = _connection()

    assert connection.status is ConnectionStatus.PENDING
    assert connection.has_credentials
    assert not connection.is_connected
    with pytest.raises(NotConnectedError):
        connection.require_access_token()


def test_completing_connect_activates_the_connection() -> None:
    connection = _connection()
    connection.complete_connect(
        access_token="token",
        refresh_token=None,
        profile=BrokerProfile(broker_user_id="XY123", display_name="Trader"),
        now=NOW,
    )

    assert connection.is_connected
    assert connection.require_access_token() == "token"
    assert connection.connected_at == NOW


def test_a_rejected_token_becomes_expired_and_is_dropped() -> None:
    """Keeping a rejected token means re-learning the rejection on every call."""
    connection = _connection()
    connection.complete_connect(access_token="t", refresh_token=None, profile=None, now=NOW)

    connection.record_rejected("token expired", LATER)

    assert connection.status is ConnectionStatus.EXPIRED
    assert connection.access_token is None
    with pytest.raises(ConnectionExpiredError):
        connection.require_access_token()


def test_disconnect_keeps_credentials_but_drops_the_token() -> None:
    connection = _connection()
    connection.complete_connect(access_token="t", refresh_token=None, profile=None, now=NOW)

    connection.disconnect(LATER)

    assert connection.access_token is None
    assert connection.has_credentials
    assert connection.status is ConnectionStatus.PENDING


def test_revoke_removes_the_credentials_too() -> None:
    connection = _connection()
    connection.complete_connect(access_token="t", refresh_token=None, profile=None, now=NOW)

    connection.revoke(LATER)

    assert connection.access_token is None
    assert not connection.has_credentials
    assert connection.status is ConnectionStatus.REVOKED
    with pytest.raises(CredentialsMissingError):
        connection.require_credentials()


def test_replacing_the_app_id_invalidates_the_existing_token() -> None:
    """A token issued under the old application cannot work with a new one."""
    connection = _connection()
    connection.complete_connect(access_token="t", refresh_token=None, profile=None, now=NOW)

    connection.replace_credentials(BrokerCredentials("ZZZZZ999AA-200", "new-secret"), LATER)

    assert connection.access_token is None
    assert connection.status is ConnectionStatus.PENDING


def test_replacing_only_the_secret_keeps_the_session() -> None:
    connection = _connection()
    connection.complete_connect(access_token="t", refresh_token=None, profile=None, now=NOW)

    connection.replace_credentials(BrokerCredentials("ABCDE123XY-100", "rotated-secret"), LATER)

    assert connection.is_connected


def test_revalidation_recovers_an_expired_connection() -> None:
    connection = _connection()
    connection.complete_connect(access_token="t", refresh_token=None, profile=None, now=NOW)
    connection.record_rejected("temporary", LATER)

    connection.record_validated(BrokerProfile("XY", "Trader"), LATER)

    assert connection.status is ConnectionStatus.ACTIVE


def test_completing_without_a_token_is_refused() -> None:
    connection = _connection()
    with pytest.raises(ValueError, match="access token"):
        connection.complete_connect(access_token="", refresh_token=None, profile=None, now=NOW)
