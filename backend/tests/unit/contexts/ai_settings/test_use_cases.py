"""Save/Get/Clear use cases over an in-memory repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from marketcompass.contexts.ai_settings.application.use_cases import (
    ClearApiKey,
    GetAiSettings,
    SaveAiSettings,
    SaveAiSettingsCommand,
)
from marketcompass.contexts.ai_settings.domain.aggregate import AiSettings
from marketcompass.contexts.ai_settings.domain.errors import ProviderUnsupportedError
from marketcompass.shared_kernel.types.identifiers import TenantId, UserId

pytestmark = pytest.mark.unit

USER = UserId(uuid.uuid4())
TENANT = TenantId(uuid.uuid4())
KEY = "sk-ant-abcd1234efgh5678"


class _FakeRepo:
    def __init__(self) -> None:
        self.saved: AiSettings | None = None

    async def find(self, user_id: UserId) -> AiSettings | None:
        return self.saved

    async def upsert(self, settings: AiSettings) -> None:
        self.saved = settings


class _FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 22, tzinfo=UTC)


class _FakeUow:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:  # pragma: no cover - not exercised here
        ...


def _command(model: str = "claude-sonnet-5") -> SaveAiSettingsCommand:
    return SaveAiSettingsCommand(
        user_id=USER, tenant_id=TENANT, provider="anthropic", api_key=KEY, model=model
    )


async def test_get_returns_default_view_when_absent() -> None:
    view = await GetAiSettings(repository=_FakeRepo())(USER)
    assert view.configured is False
    assert view.available is False
    assert view.masked_api_key is None
    assert view.provider == "anthropic"


async def test_save_creates_then_updates_the_same_row() -> None:
    repo, clock, uow = _FakeRepo(), _FakeClock(), _FakeUow()
    save = SaveAiSettings(repository=repo, clock=clock, uow=uow)

    created = await save(_command())
    assert created.configured is True
    assert created.available is True
    assert created.masked_api_key is not None and KEY not in created.masked_api_key
    first_id = repo.saved.id if repo.saved else None
    assert uow.committed is True

    updated = await save(_command(model="claude-opus-5"))
    assert updated.model == "claude-opus-5"
    # Same row reused, not a second insert.
    assert repo.saved is not None and repo.saved.id == first_id


async def test_save_rejects_unsupported_provider_before_persisting() -> None:
    repo = _FakeRepo()
    save = SaveAiSettings(repository=repo, clock=_FakeClock(), uow=_FakeUow())
    command = SaveAiSettingsCommand(
        user_id=USER, tenant_id=TENANT, provider="openai", api_key=KEY, model="gpt-x"
    )
    with pytest.raises(ProviderUnsupportedError):
        await save(command)
    assert repo.saved is None


async def test_clear_is_idempotent_when_absent() -> None:
    view = await ClearApiKey(repository=_FakeRepo(), clock=_FakeClock(), uow=_FakeUow())(USER)
    assert view.configured is False


async def test_clear_removes_the_key() -> None:
    repo, clock, uow = _FakeRepo(), _FakeClock(), _FakeUow()
    await SaveAiSettings(repository=repo, clock=clock, uow=uow)(_command())

    view = await ClearApiKey(repository=repo, clock=clock, uow=uow)(USER)
    assert view.configured is False
    assert view.available is False
    assert repo.saved is not None and repo.saved.api_key is None
