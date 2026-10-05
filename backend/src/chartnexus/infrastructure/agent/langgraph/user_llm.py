"""Build the chat model from the *calling user's* saved LLM settings.

The switch from a global env key to per-user keys lives here. Both agent builders
(HELLA and STRYX) call this so the model is constructed from the authenticated
user's own provider, key, and model — loaded and decrypted per request. When the
user has not saved a key, this returns ``None`` and the builders fall back to
their import-safe "unavailable" agent, which is what disables the AI tab.

There is deliberately no env fallback: the global ``CN_LLM_*`` key no longer
serves end users. The only still-global settings read here are operational
(max output tokens, request timeout) — never a key.

The repository import is deferred into the function body on purpose: this module
is imported statically by the agent builders, which are in turn imported by the
``copilot``/``stryx`` dependencies. Keeping the ``ai_settings`` context off this
module's top level keeps those contexts from acquiring a static edge into it,
preserving the bounded-context independence contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from chartnexus.infrastructure.agent.langgraph.llm import build_chat_model
from chartnexus.shared_kernel.types.identifiers import UserId

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


async def build_user_chat_model(
    container: Any, session: AsyncSession, user_id: UserId
) -> BaseChatModel | None:
    """The chat model for this user, or ``None`` when they have no usable key."""
    from chartnexus.infrastructure.persistence.postgresql.repositories.settings.ai_settings_repository import (  # noqa: PLC0415
        SqlAlchemyAiSettingsRepository,
    )

    repository = SqlAlchemyAiSettingsRepository(session, container.ai_settings_cipher)
    settings = await repository.find(user_id)
    if settings is None or not settings.api_key:
        return None

    llm = container.settings.llm
    return build_chat_model(
        provider=settings.provider.value,
        api_key=settings.api_key,
        model=settings.model,
        max_output_tokens=llm.max_output_tokens,
        request_timeout_seconds=llm.request_timeout_seconds,
    )
