"""Settings validation — the guardrails that keep a bad deploy from booting."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from chartnexus.bootstrap.settings import (
    DatabaseSettings,
    Environment,
    SecuritySettings,
    Settings,
)

pytestmark = pytest.mark.unit


def test_defaults_are_local_and_safe() -> None:
    settings = Settings()
    assert settings.environment is Environment.LOCAL
    assert settings.broker.provider == "mock"
    assert settings.llm.provider == "rule_based"
    settings.assert_deployment_safe()  # local: no-op


def test_sync_database_driver_is_rejected() -> None:
    """A psycopg URL would work until the first await and then deadlock."""
    with pytest.raises(PydanticValidationError, match="asyncpg"):
        DatabaseSettings(url="postgresql://user:pw@localhost:5432/db")


def test_production_rejects_default_secret_key() -> None:
    settings = Settings(
        environment=Environment.PRODUCTION,
        broker={"provider": "fyers"},
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        settings.assert_deployment_safe()


def test_production_rejects_the_mock_broker() -> None:
    settings = Settings(
        environment=Environment.PRODUCTION,
        security=SecuritySettings(
            secret_key="a-real-secret",
            encryption_key="a-real-encryption-key",
        ),
    )
    with pytest.raises(RuntimeError, match="mock"):
        settings.assert_deployment_safe()


def test_production_accepts_a_fully_configured_environment() -> None:
    settings = Settings(
        environment=Environment.PRODUCTION,
        security=SecuritySettings(
            secret_key="a-real-secret",
            encryption_key="a-real-encryption-key",
        ),
        auth={"jwt_signing_key": "a-real-jwt-signing-key-of-sufficient-length"},
        broker={"provider": "fyers"},
    )
    settings.assert_deployment_safe()


def test_production_requires_an_explicit_jwt_signing_key() -> None:
    """Inheriting the app secret couples token forgery to any secret leak."""
    settings = Settings(
        environment=Environment.PRODUCTION,
        security=SecuritySettings(
            secret_key="a-real-secret",
            encryption_key="a-real-encryption-key",
        ),
        broker={"provider": "fyers"},
    )
    with pytest.raises(RuntimeError, match="JWT_SIGNING_KEY"):
        settings.assert_deployment_safe()


def test_secrets_are_not_printed_in_a_repr() -> None:
    settings = SecuritySettings(secret_key="super-secret-value")
    assert "super-secret-value" not in repr(settings)
    assert settings.secret_key.get_secret_value() == "super-secret-value"


def test_environment_knows_when_it_is_deployed() -> None:
    assert Environment.PRODUCTION.is_deployed
    assert Environment.STAGING.is_deployed
    assert not Environment.LOCAL.is_deployed
    assert not Environment.TEST.is_deployed
