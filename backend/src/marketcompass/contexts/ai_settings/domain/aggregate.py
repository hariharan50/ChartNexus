"""The AiSettings aggregate — one user's LLM provider, key, and model.

One row per user. The secret key lives here as plaintext in memory for exactly as
long as an operation needs it; encryption is the repository's job, because the
algorithm is an infrastructure concern.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from marketcompass.contexts.ai_settings.domain.value_objects import (
    SUPPORTED_PROVIDERS,
    LlmCredentials,
    LlmProvider,
)
from marketcompass.shared_kernel.types.identifiers import (
    AiSettingsId,
    TenantId,
    UserId,
    new_id,
)

_MASK_KEEP = 4


@dataclass(slots=True)
class AiSettings:
    id: AiSettingsId
    user_id: UserId
    tenant_id: TenantId
    provider: LlmProvider
    model: str
    api_key: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # -- construction -------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        user_id: UserId,
        tenant_id: TenantId,
        credentials: LlmCredentials,
        now: datetime,
    ) -> AiSettings:
        return cls(
            id=AiSettingsId(new_id()),
            user_id=user_id,
            tenant_id=tenant_id,
            provider=credentials.provider,
            model=credentials.model,
            api_key=credentials.api_key,
            created_at=now,
            updated_at=now,
        )

    # -- behaviour ----------------------------------------------------------

    def update_credentials(self, credentials: LlmCredentials, now: datetime) -> None:
        self.provider = credentials.provider
        self.model = credentials.model
        self.api_key = credentials.api_key
        self.updated_at = now

    def clear_key(self, now: datetime) -> None:
        """Forget the key but keep the provider/model choice.

        This is what disables the agent tabs again — the row remains so the last
        chosen provider/model is remembered for the next time a key is added.
        """
        self.api_key = None
        self.updated_at = now

    # -- queries ------------------------------------------------------------

    @property
    def configured(self) -> bool:
        """A key is stored, so the agents have something to run on."""
        return bool(self.api_key)

    @property
    def available(self) -> bool:
        """A key is stored *and* the provider is one we can actually run."""
        return self.configured and self.provider in SUPPORTED_PROVIDERS

    @property
    def masked_api_key(self) -> str | None:
        if not self.api_key:
            return None
        return _mask(self.api_key)


def _mask(value: str, *, keep: int = _MASK_KEEP) -> str:
    """Show only enough of a key to recognise which one is configured."""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * 6}{value[-keep:]}"
