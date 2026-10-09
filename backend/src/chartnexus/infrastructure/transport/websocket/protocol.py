"""The wire format, in one place.

The authority is ``contracts/websocket/v1/*.schema.json``; this module is the
Python side of it. Both directions live together on purpose — a codec split
across two files is how a server starts emitting a field no client reads.

Nothing here touches Redis, FastAPI or the container: it turns text into parsed
messages and dataclasses into text, so it can be tested without a socket.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

#: Bumped only for a breaking change. Announced in ``welcome`` so a client can
#: refuse a server it does not understand instead of misreading its frames.
PROTOCOL_VERSION: Final = 1

# Error codes. Mirror the enum in contracts/websocket/v1/error.schema.json —
# a client branches on these, so they are API.
MALFORMED_FRAME: Final = "malformed_frame"
UNKNOWN_MESSAGE_TYPE: Final = "unknown_message_type"
UNKNOWN_TOPIC: Final = "unknown_topic"
TOPIC_LIMIT_EXCEEDED: Final = "topic_limit_exceeded"
NOT_AUTHENTICATED: Final = "not_authenticated"
TICKET_EXPIRED: Final = "ticket_expired"
TICKET_ALREADY_USED: Final = "ticket_already_used"
INTERNAL_ERROR: Final = "internal_error"

# Close codes. 1008 (policy violation) for a credential the client could fix by
# fetching a new ticket; 1011 (internal error) for our own failures; 1013 (try
# again later) when the server is simply full.
CLOSE_POLICY_VIOLATION: Final = 1008
CLOSE_INTERNAL_ERROR: Final = 1011
CLOSE_TRY_AGAIN_LATER: Final = 1013

#: Longest client frame accepted. A subscribe to 64 topics is well under 4 KiB;
#: anything larger is a mistake or an attempt to make the server allocate.
MAX_CLIENT_FRAME_BYTES: Final = 8192

_MAX_TOPICS_PER_MESSAGE: Final = 64
_MAX_CORRELATION_ID_LENGTH: Final = 64


class ProtocolError(Exception):
    """A client frame that cannot be honoured.

    Carries the protocol ``code`` to report and, when the frame got far enough
    to have one, the correlation id to echo.
    """

    def __init__(self, code: str, message: str, *, correlation_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.correlation_id = correlation_id


@dataclass(frozen=True, slots=True)
class Subscribe:
    topics: tuple[str, ...]
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class Unsubscribe:
    topics: tuple[str, ...]
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class Ping:
    correlation_id: str | None = None


ClientMessage = Subscribe | Unsubscribe | Ping


def decode_client_message(raw: str | bytes) -> ClientMessage:
    """Parse one client frame, or raise :class:`ProtocolError`.

    Validates shape only. Whether ``snapshots:NIFTY`` names a real stream is a
    domain question, answered by ``Topic.parse`` in ``realtime_delivery``; this
    layer must not grow a second, divergent copy of that rule.
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8", errors="replace")
    if len(raw) > MAX_CLIENT_FRAME_BYTES:
        raise ProtocolError(
            MALFORMED_FRAME,
            f"A message may not exceed {MAX_CLIENT_FRAME_BYTES} bytes.",
        )

    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise ProtocolError(MALFORMED_FRAME, "This message is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ProtocolError(MALFORMED_FRAME, "A message must be a JSON object.")

    correlation_id = _correlation_id(payload)
    kind = payload.get("type")

    if kind == "ping":
        return Ping(correlation_id=correlation_id)
    if kind == "subscribe":
        return Subscribe(topics=_topics(payload, correlation_id), correlation_id=correlation_id)
    if kind == "unsubscribe":
        return Unsubscribe(topics=_topics(payload, correlation_id), correlation_id=correlation_id)

    raise ProtocolError(
        UNKNOWN_MESSAGE_TYPE,
        "Expected 'subscribe', 'unsubscribe' or 'ping'.",
        correlation_id=correlation_id,
    )


def _correlation_id(payload: dict[str, Any]) -> str | None:
    raw = payload.get("id")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw or len(raw) > _MAX_CORRELATION_ID_LENGTH:
        raise ProtocolError(
            MALFORMED_FRAME,
            f"'id' must be a string of 1 to {_MAX_CORRELATION_ID_LENGTH} characters.",
        )
    return raw


def _topics(payload: dict[str, Any], correlation_id: str | None) -> tuple[str, ...]:
    raw = payload.get("topics")
    if not isinstance(raw, list) or not raw:
        raise ProtocolError(
            MALFORMED_FRAME,
            "'topics' must be a non-empty array.",
            correlation_id=correlation_id,
        )
    if len(raw) > _MAX_TOPICS_PER_MESSAGE:
        raise ProtocolError(
            TOPIC_LIMIT_EXCEEDED,
            f"At most {_MAX_TOPICS_PER_MESSAGE} topics per message.",
            correlation_id=correlation_id,
        )
    if not all(isinstance(item, str) and item for item in raw):
        raise ProtocolError(
            MALFORMED_FRAME,
            "Every entry in 'topics' must be a non-empty string.",
            correlation_id=correlation_id,
        )
    # De-duplicated here rather than rejected: the contract says uniqueItems, but
    # a client resending its full set after a reconnect is the behaviour we asked
    # for, and punishing a duplicate would make that awkward to write.
    return tuple(dict.fromkeys(raw))


# --------------------------------------------------------------------------
# Server to client
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SnapshotPayload:
    """The body of a ``snapshot_committed`` frame.

    ``spot`` is a string, not a float: it is a price, and JSON numbers are
    doubles. The REST surface makes the same choice, so a client parses both
    the same way.
    """

    symbol: str
    session_date: str
    captured_at: str
    source: str
    spot: str | None = None
    expiry: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "session_date": self.session_date,
            "captured_at": self.captured_at,
            "source": self.source,
            "spot": self.spot,
            "expiry": self.expiry,
        }


def welcome(*, connection_id: str, server_time: datetime) -> str:
    return _encode(
        {
            "type": "welcome",
            "connection_id": connection_id,
            "protocol_version": PROTOCOL_VERSION,
            "server_time": _rfc3339(server_time),
        }
    )


def ack(*, topics: tuple[str, ...], correlation_id: str | None = None) -> str:
    """Confirm a subscription change.

    ``topics`` is the connection's whole resulting set, so a client can assign
    rather than reconcile. Sorted for a stable frame — easier to eyeball in a
    log or a test than insertion order.
    """
    body: dict[str, Any] = {"type": "ack", "topics": sorted(topics)}
    if correlation_id is not None:
        body["id"] = correlation_id
    return _encode(body)


def snapshot_committed(*, topic: str, published_at: str, payload: SnapshotPayload) -> str:
    return _encode(
        {
            "type": "snapshot_committed",
            "topic": topic,
            "published_at": published_at,
            "payload": payload.as_dict(),
        }
    )


def pong(*, server_time: datetime, correlation_id: str | None = None) -> str:
    body: dict[str, Any] = {"type": "pong", "server_time": _rfc3339(server_time)}
    if correlation_id is not None:
        body["id"] = correlation_id
    return _encode(body)


def error(*, code: str, message: str, correlation_id: str | None = None) -> str:
    body: dict[str, Any] = {"code": code, "message": message}
    if correlation_id is not None:
        body["id"] = correlation_id
    return _encode({"type": "error", "error": body})


def _encode(body: dict[str, Any]) -> str:
    return json.dumps(body, separators=(",", ":"))


def _rfc3339(moment: datetime) -> str:
    """UTC, with a trailing ``Z``.

    ``datetime.isoformat`` renders UTC as ``+00:00``, which is valid RFC 3339
    but not what the rest of this system emits; normalising here keeps one shape
    on the wire.
    """
    return moment.isoformat().replace("+00:00", "Z")
