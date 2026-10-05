"""Composition bridge for HUGIN — assembles ports from the ``Container``.

The one module the ``hugin`` context is allowed to import from infrastructure.
Mirrors ``build_stryx.py``: it lives here (not in the context) so the context
never acquires a static edge into infrastructure/other contexts, and the
independence contract exempts only the single edge
``hugin.api.dependencies -> infrastructure.hugin.build_hugin``.

Provides the *read* services (the API/UI side) and the *reflector* (the LLM
judge/read step, built from the tenant owner's key). The full worker-side
``build_hugin_cycle`` composition lands with the worker in a later phase.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from chartnexus.contexts.hugin.application.ask_hugin import AskHugin
from chartnexus.contexts.hugin.application.enrollment import (
    GetHuginEnrollment,
    SetHuginEnrollment,
)
from chartnexus.contexts.hugin.application.generate_call import (
    GenerateHuginCall,
    GetHuginCalls,
)
from chartnexus.contexts.hugin.application.get_history import GetHuginHistory
from chartnexus.contexts.hugin.application.get_memory import GetHuginMemory
from chartnexus.contexts.hugin.application.ports import (
    CallGeneratorPort,
    ChatPort,
    MarketReaderPort,
    MemoryStorePort,
    ReflectorPort,
    SessionStorePort,
    TenantDirectoryPort,
)
from chartnexus.infrastructure.agent.langgraph.user_llm import build_user_chat_model
from chartnexus.infrastructure.hugin.market_reader import ToolMarketReader
from chartnexus.infrastructure.hugin.redis_session_store import HuginRedisSessionStore
from chartnexus.infrastructure.hugin.tenant_directory import SqlAlchemyTenantDirectory
from chartnexus.infrastructure.persistence.postgresql.repositories.hugin.call_repository import (
    SqlAlchemyHuginCallRepository,
)
from chartnexus.infrastructure.persistence.postgresql.repositories.hugin.enrollment_repository import (
    SqlAlchemyHuginEnrollmentRepository,
)
from chartnexus.infrastructure.persistence.postgresql.repositories.hugin.memory_repository import (
    SqlAlchemyHuginMemoryRepository,
)
from chartnexus.infrastructure.transport.http.dependencies import get_container
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId

# How many trading days of memory HUGIN's chat/call digest looks back over.
_CHAT_HISTORY_DAYS = 7
# How many recent calls the UI lists.
_CALLS_LIMIT = 20


@dataclass(slots=True)
class HuginReadServices:
    """The read/settings side of HUGIN, wired for one authenticated request."""

    memory: GetHuginMemory
    #: HUGIN's multi-day track record for the "watch it sharpen" view.
    history: GetHuginHistory
    #: Whether the caller has a usable LLM key — i.e. whether HUGIN *could* produce
    #: memory for them. Gates the tab, mirroring HELLA/STRYX availability.
    available: bool
    #: The per-tenant opt-in read/write use cases behind the Settings toggle.
    get_enrollment: GetHuginEnrollment
    set_enrollment: SetHuginEnrollment


async def build_hugin_read_services(
    request: Request, session: AsyncSession, user_id: UserId
) -> HuginReadServices:
    container = get_container(request)
    store = SqlAlchemyHuginMemoryRepository(container.database)
    memory = GetHuginMemory(store, lessons_top_k=container.settings.hugin.lessons_top_k)
    available = await _has_llm_key(container, session, user_id)
    enrollment = SqlAlchemyHuginEnrollmentRepository(container.database)
    return HuginReadServices(
        memory=memory,
        history=GetHuginHistory(store),
        available=available,
        get_enrollment=GetHuginEnrollment(enrollment),
        set_enrollment=SetHuginEnrollment(enrollment),
    )


async def build_hugin_reflector(
    container: Any, session: AsyncSession, user_id: UserId
) -> ReflectorPort:
    """The reflector for one tenant, built from its owner's saved LLM key.

    Returns the import-safe ``UnavailableReflector`` when the owner has no usable
    key (or the ``agent`` extra isn't installed), so the worker and the
    availability check answer without pulling in the LangChain stack — the same
    fallback shape STRYX uses.
    """
    model = await build_user_chat_model(container, session, user_id)
    if model is None:
        from chartnexus.infrastructure.agent.langgraph.hugin_unavailable import (  # noqa: PLC0415
            UnavailableReflector,
        )

        return UnavailableReflector()

    from chartnexus.infrastructure.agent.langgraph.hugin_reflector import (  # noqa: PLC0415
        HuginReflector,
    )

    return HuginReflector(model)


@dataclass(slots=True)
class HuginCycleServices:
    """The worker-side ports for running cycles, shared across tenants in a tick.

    ``store``, ``market`` and ``directory`` are tenant-agnostic. ``reflector_for``
    builds a per-tenant reflector from the owner's key (opening its own short
    session), so each tenant reflects on its own model.
    """

    directory: TenantDirectoryPort
    market: MarketReaderPort
    store: MemoryStorePort
    reflector_for: Callable[[UserId], Awaitable[ReflectorPort]]
    lessons_top_k: int


def build_hugin_cycle(container: Any) -> HuginCycleServices:
    """Assemble the worker-side services from a ``Container`` (no request scope)."""

    async def reflector_for(user_id: UserId) -> ReflectorPort:
        # A short read session just to load the owner's key and build the model;
        # the model holds no session reference once built.
        async with container.database.read_session() as session:
            return await build_hugin_reflector(container, session, user_id)

    return HuginCycleServices(
        directory=SqlAlchemyTenantDirectory(container.database),
        market=ToolMarketReader(container),
        store=SqlAlchemyHuginMemoryRepository(container.database),
        reflector_for=reflector_for,
        lessons_top_k=container.settings.hugin.lessons_top_k,
    )


@dataclass(slots=True)
class HuginChatServices:
    """HUGIN's memory-grounded chat, wired for one authenticated request."""

    ask: AskHugin
    sessions: SessionStorePort


async def build_hugin_chat_services(
    request: Request, session: AsyncSession, user_id: UserId, tenant_id: TenantId
) -> HuginChatServices:
    container = get_container(request)
    agent = await _build_chat_agent(container, session, user_id)
    store = SqlAlchemyHuginMemoryRepository(container.database)
    ask = AskHugin(
        agent=agent,
        store=store,
        lessons_top_k=container.settings.hugin.lessons_top_k,
        history_days=_CHAT_HISTORY_DAYS,
    )
    sessions = HuginRedisSessionStore(container.redis, tenant_id)
    return HuginChatServices(ask=ask, sessions=sessions)


async def _build_chat_agent(container: Any, session: AsyncSession, user_id: UserId) -> ChatPort:
    model = await build_user_chat_model(container, session, user_id)
    if model is None:
        from chartnexus.infrastructure.agent.langgraph.hugin_chat_unavailable import (  # noqa: PLC0415
            UnavailableHuginChat,
        )

        return UnavailableHuginChat()

    from chartnexus.infrastructure.agent.langgraph.hugin_chat import (  # noqa: PLC0415
        HuginChatAgent,
    )

    return HuginChatAgent(model)


@dataclass(slots=True)
class HuginCallServices:
    """HUGIN's memory-driven calls, wired for one authenticated request."""

    generate: GenerateHuginCall
    recent: GetHuginCalls


async def build_hugin_call_services(
    request: Request, session: AsyncSession, user_id: UserId
) -> HuginCallServices:
    container = get_container(request)
    generator = await _build_caller(container, session, user_id)
    store = SqlAlchemyHuginMemoryRepository(container.database)
    calls = SqlAlchemyHuginCallRepository(container.database)
    generate = GenerateHuginCall(
        generator=generator,
        store=store,
        calls=calls,
        lessons_top_k=container.settings.hugin.lessons_top_k,
        history_days=_CHAT_HISTORY_DAYS,
    )
    return HuginCallServices(generate=generate, recent=GetHuginCalls(calls, limit=_CALLS_LIMIT))


async def _build_caller(
    container: Any, session: AsyncSession, user_id: UserId
) -> CallGeneratorPort:
    model = await build_user_chat_model(container, session, user_id)
    if model is None:
        from chartnexus.infrastructure.agent.langgraph.hugin_caller_unavailable import (  # noqa: PLC0415
            UnavailableHuginCaller,
        )

        return UnavailableHuginCaller()

    from chartnexus.infrastructure.agent.langgraph.hugin_caller import (  # noqa: PLC0415
        HuginCaller,
    )

    return HuginCaller(model)


async def _has_llm_key(container: object, session: AsyncSession, user_id: UserId) -> bool:
    """True when this user has saved an LLM key — checked without loading LangChain.

    Deferred import so the ``hugin`` context (which reaches this module only through
    the read-services builder) never acquires a static edge into ``ai_settings``.
    """
    from chartnexus.infrastructure.persistence.postgresql.repositories.settings.ai_settings_repository import (  # noqa: PLC0415
        SqlAlchemyAiSettingsRepository,
    )

    repository = SqlAlchemyAiSettingsRepository(session, container.ai_settings_cipher)  # type: ignore[attr-defined]
    settings = await repository.find(user_id)
    return settings is not None and settings.available
