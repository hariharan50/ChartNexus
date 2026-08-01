"""Refresh sessions: rotation, families, and reuse detection.

A session is a *family* of refresh tokens. Each refresh swaps the presented
token for a new one and marks the old one used. If a token that was already used
comes back, the family is assumed compromised — the legitimate client and an
attacker now both hold tokens — and the whole family is revoked.

Only the SHA-256 of a refresh token is stored. A database leak therefore yields
no usable tokens.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from marketcompass.shared_kernel.types.identifiers import SessionId, TenantId, UserId, new_id

# 32 bytes from the system CSPRNG: the token is a bearer secret, so its only
# defence is being unguessable.
_TOKEN_BYTES = 32


class SessionRevocationReason(StrEnum):
    LOGOUT = "logout"
    LOGOUT_ALL = "logout_all"
    ROTATED = "rotated"
    REUSE_DETECTED = "reuse_detected"
    EXPIRED = "expired"
    PASSWORD_CHANGED = "password_changed"  # noqa: S105 — reason label
    ADMIN_REVOKED = "admin_revoked"
    SESSION_LIMIT = "session_limit"


@dataclass(frozen=True, slots=True)
class IssuedRefreshToken:
    """The raw token, returned to the caller exactly once."""

    value: str
    token_hash: str
    expires_at: datetime

    def __repr__(self) -> str:
        return f"IssuedRefreshToken(hash={self.token_hash[:8]}…)"


@dataclass(slots=True)
class RefreshSession:
    """One device's session. ``family_id`` ties successive rotations together."""

    id: SessionId
    family_id: SessionId
    user_id: UserId
    tenant_id: TenantId
    token_hash: str
    issued_at: datetime
    expires_at: datetime
    user_agent: str | None = None
    ip_address: str | None = None
    used_at: datetime | None = None
    revoked_at: datetime | None = None
    revocation_reason: SessionRevocationReason | None = None
    replaced_by_id: SessionId | None = None
    generation: int = 0
    metadata: dict[str, str] = field(default_factory=dict)

    # -- construction -------------------------------------------------------

    @classmethod
    def start(
        cls,
        *,
        user_id: UserId,
        tenant_id: TenantId,
        now: datetime,
        ttl_seconds: int,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[RefreshSession, IssuedRefreshToken]:
        session_id = SessionId(new_id())
        token = _generate_token(now, ttl_seconds)
        session = cls(
            id=session_id,
            family_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            token_hash=token.token_hash,
            issued_at=now,
            expires_at=token.expires_at,
            user_agent=_truncate(user_agent, 400),
            ip_address=_truncate(ip_address, 45),
        )
        return session, token

    # -- queries ------------------------------------------------------------

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def is_active(self, now: datetime) -> bool:
        return not self.is_revoked and not self.is_used and not self.is_expired(now)

    def matches(self, presented_token: str) -> bool:
        """Constant-time comparison against the stored hash."""
        return secrets.compare_digest(self.token_hash, hash_token(presented_token))

    def within_reuse_grace(self, now: datetime, grace_seconds: int) -> bool:
        """True if this token was rotated moments ago.

        Two tabs refreshing at once both present the same token; the loser would
        otherwise trip reuse detection and log the user out.
        """
        if self.used_at is None:
            return False
        return (now - self.used_at).total_seconds() <= grace_seconds

    # -- behaviour ----------------------------------------------------------

    def rotate(
        self,
        *,
        now: datetime,
        ttl_seconds: int,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[RefreshSession, IssuedRefreshToken]:
        """Consume this token and issue its successor in the same family."""
        successor_id = SessionId(new_id())
        token = _generate_token(now, ttl_seconds)

        self.used_at = now
        self.replaced_by_id = successor_id

        successor = RefreshSession(
            id=successor_id,
            family_id=self.family_id,
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            token_hash=token.token_hash,
            issued_at=now,
            # Rotation must not extend a session indefinitely; the family's
            # original expiry is the ceiling.
            expires_at=min(token.expires_at, self.expires_at),
            user_agent=_truncate(user_agent, 400) or self.user_agent,
            ip_address=_truncate(ip_address, 45) or self.ip_address,
            generation=self.generation + 1,
            metadata=dict(self.metadata),
        )
        return successor, IssuedRefreshToken(
            value=token.value,
            token_hash=token.token_hash,
            expires_at=successor.expires_at,
        )

    def revoke(self, reason: SessionRevocationReason, now: datetime) -> None:
        if self.is_revoked:
            return
        self.revoked_at = now
        self.revocation_reason = reason


def hash_token(token: str) -> str:
    """SHA-256 hex digest.

    A fast hash is correct here, unlike for passwords: the token already has 256
    bits of entropy, so there is nothing to brute-force and nothing to slow down.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_token(now: datetime, ttl_seconds: int) -> IssuedRefreshToken:
    value = secrets.token_urlsafe(_TOKEN_BYTES)
    return IssuedRefreshToken(
        value=value,
        token_hash=hash_token(value),
        expires_at=now + timedelta(seconds=ttl_seconds),
    )


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned[:limit] if cleaned else None
