"""Refresh session repository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from marketcompass.contexts.identity.domain.refresh_session import (
    RefreshSession,
    SessionRevocationReason,
)
from marketcompass.infrastructure.persistence.postgresql.models.identity.refresh_session import (
    RefreshSessionRecord,
)
from marketcompass.shared_kernel.types.identifiers import SessionId, TenantId, UserId


class SqlAlchemyRefreshSessionRepository:
    """Implements the ``RefreshSessionRepository`` port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, session_id: SessionId) -> RefreshSession | None:
        record = await self._session.get(RefreshSessionRecord, session_id)
        return _to_domain(record) if record else None

    async def find_by_token_hash(self, token_hash: str) -> RefreshSession | None:
        result = await self._session.execute(
            select(RefreshSessionRecord).where(RefreshSessionRecord.token_hash == token_hash)
        )
        record = result.scalar_one_or_none()
        return _to_domain(record) if record else None

    async def add(self, session: RefreshSession) -> None:
        self._session.add(
            RefreshSessionRecord(
                id=session.id,
                family_id=session.family_id,
                user_id=session.user_id,
                tenant_id=session.tenant_id,
                token_hash=session.token_hash,
                issued_at=session.issued_at,
                expires_at=session.expires_at,
                used_at=session.used_at,
                revoked_at=session.revoked_at,
                revocation_reason=(
                    session.revocation_reason.value if session.revocation_reason else None
                ),
                replaced_by_id=session.replaced_by_id,
                generation=session.generation,
                user_agent=session.user_agent,
                ip_address=session.ip_address,
            )
        )
        await self._session.flush()

    async def update(self, session: RefreshSession) -> None:
        record = await self._session.get(RefreshSessionRecord, session.id)
        if record is None:
            msg = f"refresh session {session.id} disappeared between load and save"
            raise LookupError(msg)

        record.used_at = session.used_at
        record.revoked_at = session.revoked_at
        record.revocation_reason = (
            session.revocation_reason.value if session.revocation_reason else None
        )
        record.replaced_by_id = session.replaced_by_id
        await self._session.flush()

    async def list_active_for_user(self, user_id: UserId) -> list[RefreshSession]:
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(RefreshSessionRecord).where(
                RefreshSessionRecord.user_id == user_id,
                RefreshSessionRecord.revoked_at.is_(None),
                RefreshSessionRecord.used_at.is_(None),
                RefreshSessionRecord.expires_at > now,
            )
        )
        return [_to_domain(record) for record in result.scalars()]

    async def revoke_family(
        self,
        family_id: SessionId,
        reason: SessionRevocationReason,
        now: datetime,
    ) -> int:
        # A set-based update: a compromised family can hold many rows, and this
        # must be one statement so no token survives a partial revocation.
        result: CursorResult[Any] = await self._session.execute(  # type: ignore[assignment]
            update(RefreshSessionRecord)
            .where(
                RefreshSessionRecord.family_id == family_id,
                RefreshSessionRecord.revoked_at.is_(None),
            )
            .values(revoked_at=now, revocation_reason=reason.value)
        )
        await self._session.flush()
        return int(result.rowcount or 0)

    async def revoke_all_for_user(
        self,
        user_id: UserId,
        reason: SessionRevocationReason,
        now: datetime,
        *,
        except_session_id: SessionId | None = None,
    ) -> int:
        statement = (
            update(RefreshSessionRecord)
            .where(
                RefreshSessionRecord.user_id == user_id,
                RefreshSessionRecord.revoked_at.is_(None),
            )
            .values(revoked_at=now, revocation_reason=reason.value)
        )
        if except_session_id is not None:
            statement = statement.where(RefreshSessionRecord.id != except_session_id)

        result: CursorResult[Any] = await self._session.execute(statement)  # type: ignore[assignment]
        await self._session.flush()
        return int(result.rowcount or 0)

    async def delete_expired(self, before: datetime) -> int:
        """Housekeeping for the scheduled cleanup task."""
        result: CursorResult[Any] = await self._session.execute(  # type: ignore[assignment]
            delete(RefreshSessionRecord).where(RefreshSessionRecord.expires_at < before)
        )
        return int(result.rowcount or 0)


def _to_domain(record: RefreshSessionRecord) -> RefreshSession:
    return RefreshSession(
        id=SessionId(record.id),
        family_id=SessionId(record.family_id),
        user_id=UserId(record.user_id),
        tenant_id=TenantId(record.tenant_id),
        token_hash=record.token_hash,
        issued_at=_aware(record.issued_at),
        expires_at=_aware(record.expires_at),
        user_agent=record.user_agent,
        ip_address=record.ip_address,
        used_at=_optional_aware(record.used_at),
        revoked_at=_optional_aware(record.revoked_at),
        revocation_reason=(
            SessionRevocationReason(record.revocation_reason) if record.revocation_reason else None
        ),
        replaced_by_id=SessionId(record.replaced_by_id) if record.replaced_by_id else None,
        generation=record.generation,
    )


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _optional_aware(moment: datetime | None) -> datetime | None:
    return _aware(moment) if moment is not None else None
