"""Typed identifiers.

Distinct types rather than bare UUIDs: passing a TenantId where a UserId is
expected is the kind of mistake that silently returns another tenant's data, and
it should not survive type-checking.
"""

from __future__ import annotations

import time
import uuid
from typing import NewType

UserId = NewType("UserId", uuid.UUID)
TenantId = NewType("TenantId", uuid.UUID)
SessionId = NewType("SessionId", uuid.UUID)
OrganizationId = NewType("OrganizationId", uuid.UUID)
InstrumentId = NewType("InstrumentId", uuid.UUID)
BrokerConnectionId = NewType("BrokerConnectionId", uuid.UUID)
AiSettingsId = NewType("AiSettingsId", uuid.UUID)
MessagingChannelId = NewType("MessagingChannelId", uuid.UUID)
SignalId = NewType("SignalId", uuid.UUID)
AuditEntryId = NewType("AuditEntryId", uuid.UUID)


def new_id() -> uuid.UUID:
    """Generate a time-ordered UUIDv7.

    Matches the ``uuidv7()`` default in Postgres so identifiers created by the
    application and by the database sort the same way. Python's stdlib gains
    ``uuid7`` in 3.14; this implements RFC 9562 directly so the behaviour does
    not depend on the interpreter version.
    """
    timestamp_ms = _now_ms()
    raw = bytearray(uuid.uuid4().bytes)
    raw[0:6] = timestamp_ms.to_bytes(6, "big")
    raw[6] = 0x70 | (raw[6] & 0x0F)  # version 7
    raw[8] = 0x80 | (raw[8] & 0x3F)  # RFC 4122 variant
    return uuid.UUID(bytes=bytes(raw))


def _now_ms() -> int:
    return int(time.time() * 1000)


def parse_id(value: str) -> uuid.UUID:
    """Parse an identifier from untrusted input."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        msg = f"{value!r} is not a valid identifier"
        raise ValueError(msg) from exc
