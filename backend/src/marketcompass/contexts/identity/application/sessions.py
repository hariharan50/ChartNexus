"""Refresh, logout, and the current-user query."""

from __future__ import annotations

from dataclasses import dataclass, field

from marketcompass.contexts.identity.application.dto import (
    AuthenticationResult,
    RequestContextInput,
    SessionView,
    UserView,
)
from marketcompass.contexts.identity.application.ports import (
    RefreshSessionRepository,
    UnitOfWork,
    UserRepository,
)
from marketcompass.contexts.identity.application.session_service import SessionService
from marketcompass.contexts.identity.domain.errors import SessionExpiredError
from marketcompass.shared_kernel.domain.errors import NotFoundError
from marketcompass.shared_kernel.types.identifiers import SessionId, UserId


@dataclass(frozen=True, slots=True)
class RefreshCommand:
    refresh_token: str
    context: RequestContextInput = field(default_factory=RequestContextInput)


@dataclass(frozen=True, slots=True)
class LogoutCommand:
    refresh_token: str | None


class RefreshSessionTokens:
    def __init__(
        self,
        *,
        users: UserRepository,
        sessions: SessionService,
        uow: UnitOfWork,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._uow = uow

    async def __call__(self, command: RefreshCommand) -> AuthenticationResult:
        if not command.refresh_token:
            raise SessionExpiredError("No refresh token was supplied.")

        user, tokens = await self._sessions.rotate(
            command.refresh_token,
            self._users.get,
            command.context,
        )
        await self._uow.commit()
        return AuthenticationResult(user=UserView.of(user), tokens=tokens)


class Logout:
    def __init__(self, *, sessions: SessionService, uow: UnitOfWork) -> None:
        self._sessions = sessions
        self._uow = uow

    async def __call__(self, command: LogoutCommand) -> None:
        await self._sessions.end(command.refresh_token)
        await self._uow.commit()


class LogoutEverywhere:
    def __init__(
        self,
        *,
        users: UserRepository,
        sessions: SessionService,
        uow: UnitOfWork,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._uow = uow

    async def __call__(self, user_id: UserId) -> int:
        user = await self._users.get(user_id)
        if user is None:
            raise NotFoundError("user", user_id)
        revoked = await self._sessions.end_all(user)
        await self._uow.commit()
        return revoked


class GetCurrentUser:
    def __init__(self, *, users: UserRepository) -> None:
        self._users = users

    async def __call__(self, user_id: UserId) -> UserView:
        user = await self._users.get(user_id)
        if user is None:
            # The access token is valid but the account is gone — treat it as an
            # expired session rather than a 404, so the client signs out.
            raise SessionExpiredError
        return UserView.of(user)


class ListSessions:
    def __init__(self, *, sessions_repository: RefreshSessionRepository) -> None:
        self._sessions = sessions_repository

    async def __call__(self, user_id: UserId, current: SessionId | None) -> list[SessionView]:
        active = await self._sessions.list_active_for_user(user_id)
        return [
            SessionView(
                id=session.id,
                created_at=session.issued_at,
                expires_at=session.expires_at,
                user_agent=session.user_agent,
                ip_address=session.ip_address,
                is_current=session.id == current,
            )
            for session in sorted(active, key=lambda item: item.issued_at, reverse=True)
        ]
