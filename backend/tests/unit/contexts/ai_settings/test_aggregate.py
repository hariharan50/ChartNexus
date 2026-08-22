"""The AiSettings aggregate — configured/available/masked and lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from marketcompass.contexts.ai_settings.domain.aggregate import AiSettings
from marketcompass.contexts.ai_settings.domain.value_objects import LlmCredentials, LlmProvider
from marketcompass.shared_kernel.types.identifiers import TenantId, UserId

pytestmark = pytest.mark.unit

USER = UserId(uuid.uuid4())
TENANT = TenantId(uuid.uuid4())
NOW = datetime(2026, 8, 22, tzinfo=UTC)
KEY = "sk-ant-abcd1234efgh5678"


def _creds(model: str = "claude-sonnet-5") -> LlmCredentials:
    return LlmCredentials.parse("anthropic", KEY, model)


def _settings() -> AiSettings:
    return AiSettings.create(user_id=USER, tenant_id=TENANT, credentials=_creds(), now=NOW)


def test_create_is_configured_and_available() -> None:
    settings = _settings()
    assert settings.provider is LlmProvider.ANTHROPIC
    assert settings.api_key == KEY
    assert settings.configured is True
    assert settings.available is True


def test_masked_key_hides_the_middle() -> None:
    settings = _settings()
    masked = settings.masked_api_key
    assert masked is not None
    assert KEY not in masked
    assert masked.startswith("sk-a")
    assert masked.endswith(KEY[-4:])


def test_update_replaces_provider_key_and_model() -> None:
    settings = _settings()
    later = datetime(2026, 8, 23, tzinfo=UTC)
    settings.update_credentials(_creds(model="claude-opus-5"), later)
    assert settings.model == "claude-opus-5"
    assert settings.updated_at == later


def test_clear_key_keeps_choice_but_disables() -> None:
    settings = _settings()
    settings.clear_key(NOW)
    assert settings.api_key is None
    assert settings.configured is False
    assert settings.available is False
    assert settings.masked_api_key is None
    # Provider/model are remembered for the next time a key is added.
    assert settings.provider is LlmProvider.ANTHROPIC
    assert settings.model == "claude-sonnet-5"
