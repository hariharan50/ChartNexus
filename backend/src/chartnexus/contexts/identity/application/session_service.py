"""Session issuance, rotation, and revocation.

Shared by password login and Google login so that both produce identical
sessions — one place decides how long a session lives and how many a user may
hold at once.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from chartnexus.contexts.identity.application.dto import (
    RequestContextInput,
    TokenPair,
)
from chartnexus.contexts.identity.application.ports import (
    AccessTokenIssuer,
    Clock,
    RefreshSessionRepository,
    UnitOfWork,
)
from chartnexus.contexts.identity.domain.errors import (
    SessionExpiredError,
    TokenReuseDetectedError,
)
from chartnexus.contexts.identity.domain.refresh_session import (
    RefreshSession,
    SessionRevocationReason,
    hash_token,
)
from chartnexus.contexts.identity.domain.user import User
from chartnexus.shared_kernel.types.identifiers import UserId

UserLoader = Callable[[UserId], Awaitable[User | None]]


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    refresh_ttl_seconds: int
    reuse_grace_seconds: int
    max_active_sessions: int


class SessionService:
    def __init__(
        self,
        *,
        sessions: RefreshSessionRepository,
        tokens: AccessTokenIssuer,
        clock: Clock,
        policy: SessionPolicy,
        uow: UnitOfWork,
    ) -> None:
        self._sessions = sessions
        self._tokens = tokens
        self._clock = clock
        self._policy = policy
        self._uow = uow

    async def start(self, user: User, context: RequestContextInput) -> TokenPair:
        now = self._clock.now()
        await self._enforce_session_limit(user, now)

        session, refresh_token = RefreshSession.start(
            user_id=user.id,
            tenant_id=user.tenant_id,
            now=now,
            ttl_seconds=self._policy.refresh_ttl_seconds,
            user_agent=context.user_agent,
            ip_address=context.ip_address,
        )
        await self._sessions.add(session)

        access = self._tokens.issue(
            user_id=user.id,
            tenant_id=user.tenant_id,
            session_id=session.id,
            roles=frozenset(role.value for role in user.roles),
            email=user.email.value,
            now=now,
        )
        return TokenPair(
            access_token=access.value,
            access_token_expires_at=access.expires_at,
            access_token_expires_in=access.expires_in_seconds,
            refresh_token=refresh_token.value,
            refresh_token_expires_at=refresh_token.expires_at,
            session_id=session.id,
        )

    async def rotate(
        self,
        presented_token: str,
        user_loader: UserLoader,
        context: RequestContextInput,
    ) -> tuple[User, TokenPair]:
        """Exchange a refresh token for a new pair.

        Every failure path here ends in the user signing in again; none of them
        reveal whether the token was unknown, expired, or revoked.
        """
        now = self._clock.now()
        session = await self._sessions.find_by_token_hash(hash_token(presented_token))
        if session is None:
            raise SessionExpiredError

        if session.is_used:
            # The token was already rotated. Unless this is the tail of a race
            # between two tabs, someone is replaying a stolen token.
            if not session.within_reuse_grace(now, self._policy.reuse_grace_seconds):
                await self._sessions.revoke_family(
                    session.family_id, SessionRevocationReason.REUSE_DETECTED, now
                )
                # Commit before raising. The error aborts the request, and an
                # abort rolls the transaction back — which would silently undo
                # the revocation and leave the stolen token usable.
                await self._uow.commit()
                raise TokenReuseDetectedError
            raise SessionExpiredError

        if session.is_revoked:
            raise TokenReuseDetectedError

        if session.is_expired(now):
            session.revoke(SessionRevocationReason.EXPIRED, now)
            await self._sessions.update(session)
            await self._uow.commit()
            raise SessionExpiredError

        user = await user_loader(session.user_id)
        if user is None:
            await self._sessions.revoke_family(
                session.family_id, SessionRevocationReason.ADMIN_REVOKED, now
            )
            await self._uow.commit()
            raise SessionExpiredError
        user.ensure_can_authenticate()

        successor, refresh_token = session.rotate(
            now=now,
            ttl_seconds=self._policy.refresh_ttl_seconds,
            user_agent=context.user_agent,
            ip_address=context.ip_address,
        )
        await self._sessions.update(session)
        await self._sessions.add(successor)

        access = self._tokens.issue(
            user_id=user.id,
            tenant_id=user.tenant_id,
            session_id=successor.id,
            roles=frozenset(role.value for role in user.roles),
            email=user.email.value,
            now=now,
        )
        return user, TokenPair(
            access_token=access.value,
            access_token_expires_at=access.expires_at,
            access_token_expires_in=access.expires_in_seconds,
            refresh_token=refresh_token.value,
            refresh_token_expires_at=refresh_token.expires_at,
            session_id=successor.id,
        )

    async def end(self, presented_token: str | None) -> None:
        """Revoke the family behind a refresh token.

        Logout is idempotent and never errors: a client that has lost its token
        is already logged out, and saying so achieves nothing.
        """
        if not presented_token:
            return
        now = self._clock.now()
        session = await self._sessions.find_by_token_hash(hash_token(presented_token))
        if session is None:
            return
        await self._sessions.revoke_family(session.family_id, SessionRevocationReason.LOGOUT, now)

    async def end_all(self, user: User) -> int:
        """Revoke every session this user holds, on every device."""
        now = self._clock.now()
        return await self._sessions.revoke_all_for_user(
            user.id, SessionRevocationReason.LOGOUT_ALL, now
        )

    async def _enforce_session_limit(self, user: User, now: datetime) -> None:
        active = await self._sessions.list_active_for_user(user.id)
        overflow = len(active) - self._policy.max_active_sessions + 1
        if overflow <= 0:
            return
        # Oldest first: a user signing in on a new device should not lose the
        # device they are actively using.
        for session in sorted(active, key=lambda item: item.issued_at)[:overflow]:
            await self._sessions.revoke_family(
                session.family_id, SessionRevocationReason.SESSION_LIMIT, now
            )
