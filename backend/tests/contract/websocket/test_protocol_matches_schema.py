"""The codec against the published schemas.

``contracts/`` is the source of truth, and ``protocol.py`` is the Python side of
it. Nothing stops the two from drifting except a test that reads both, so this
one does — structurally, without a JSON Schema library, because adding a
dependency to assert this would be a poor trade for what it buys.

What it checks is what actually drifts in practice:

* every frame the server can emit is a declared ``oneOf`` variant;
* every key in an emitted frame is declared for that variant, and every
  ``required`` key is present;
* the error codes the code can send are exactly the schema's enum — the one
  clients branch on.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from chartnexus.contexts.realtime_delivery.domain.topics import Topic
from chartnexus.infrastructure.transport.websocket import protocol

CONTRACTS = Path(__file__).resolve().parents[3].parent / "contracts" / "websocket" / "v1"

SERVER_TIME = datetime(2026, 10, 9, 8, 30, 15, tzinfo=UTC)


def _schema(name: str) -> dict[str, Any]:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def server_schema() -> dict[str, Any]:
    return _schema("server-message.schema.json")


@pytest.fixture(scope="module")
def client_schema() -> dict[str, Any]:
    return _schema("client-message.schema.json")


@pytest.fixture(scope="module")
def error_schema() -> dict[str, Any]:
    return _schema("error.schema.json")


def test_the_contracts_are_not_empty() -> None:
    """A 0-byte schema would make every assertion below vacuous."""
    for name in (
        "client-message.schema.json",
        "server-message.schema.json",
        "error.schema.json",
    ):
        assert (CONTRACTS / name).stat().st_size > 0, f"{name} is empty"


def _variants(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map each ``oneOf`` variant to its declared body, keyed by its ``type`` const."""
    found: dict[str, dict[str, Any]] = {}
    for ref in schema["oneOf"]:
        definition = schema["$defs"][ref["$ref"].rsplit("/", 1)[-1]]
        const = definition["properties"]["type"]["const"]
        found[const] = definition
    return found


def _emitted_frames() -> dict[str, dict[str, Any]]:
    """One of every frame the server can send, fully populated."""
    return {
        "welcome": json.loads(protocol.welcome(connection_id="abc123", server_time=SERVER_TIME)),
        "ack": json.loads(protocol.ack(topics=("snapshots:NIFTY",), correlation_id="r1")),
        "snapshot_committed": json.loads(
            protocol.snapshot_committed(
                topic="snapshots:NIFTY",
                published_at="2026-10-09T08:30:15Z",
                payload=protocol.SnapshotPayload(
                    symbol="NIFTY",
                    session_date="2026-10-09",
                    captured_at="2026-10-09T08:30:00Z",
                    source="mock",
                    spot="24500.50",
                    expiry="2026-10-14",
                ),
            )
        ),
        "pong": json.loads(protocol.pong(server_time=SERVER_TIME, correlation_id="r1")),
        "error": json.loads(
            protocol.error(code=protocol.UNKNOWN_TOPIC, message="Nope.", correlation_id="r1")
        ),
    }


class TestServerMessages:
    def test_every_emitted_type_is_declared(self, server_schema: dict[str, Any]) -> None:
        assert set(_emitted_frames()) == set(_variants(server_schema))

    @pytest.mark.parametrize("kind", list(_emitted_frames()))
    def test_no_undeclared_keys(self, kind: str, server_schema: dict[str, Any]) -> None:
        """A field the server sends that no client is told about."""
        frame = _emitted_frames()[kind]
        declared = set(_variants(server_schema)[kind]["properties"])

        assert set(frame) <= declared, f"{kind} sends undeclared {set(frame) - declared}"

    @pytest.mark.parametrize("kind", list(_emitted_frames()))
    def test_required_keys_are_present(self, kind: str, server_schema: dict[str, Any]) -> None:
        frame = _emitted_frames()[kind]
        required = set(_variants(server_schema)[kind].get("required", ()))

        assert required <= set(frame), f"{kind} is missing {required - set(frame)}"

    def test_the_snapshot_payload_matches_its_definition(
        self, server_schema: dict[str, Any]
    ) -> None:
        payload = _emitted_frames()["snapshot_committed"]["payload"]
        definition = server_schema["$defs"]["snapshotPayload"]

        assert set(payload) <= set(definition["properties"])
        assert set(definition["required"]) <= set(payload)

    def test_the_declared_protocol_version_agrees(self, server_schema: dict[str, Any]) -> None:
        declared = _variants(server_schema)["welcome"]["properties"]["protocol_version"]["const"]

        assert declared == protocol.PROTOCOL_VERSION

    def test_source_values_are_within_the_declared_enum(
        self, server_schema: dict[str, Any]
    ) -> None:
        """`live` and `mock` are what the ingest publisher can send."""
        allowed = set(server_schema["$defs"]["snapshotPayload"]["properties"]["source"]["enum"])

        assert {"live", "mock"} == allowed


class TestErrorCodes:
    def test_the_code_constants_are_exactly_the_schema_enum(
        self, error_schema: dict[str, Any]
    ) -> None:
        """Clients branch on these, so an undeclared code is a broken client."""
        declared = set(error_schema["properties"]["code"]["enum"])
        in_code = {
            protocol.MALFORMED_FRAME,
            protocol.UNKNOWN_MESSAGE_TYPE,
            protocol.UNKNOWN_TOPIC,
            protocol.TOPIC_LIMIT_EXCEEDED,
            protocol.NOT_AUTHENTICATED,
            protocol.TICKET_EXPIRED,
            protocol.TICKET_ALREADY_USED,
            protocol.INTERNAL_ERROR,
        }

        assert in_code == declared

    def test_an_emitted_error_body_matches_the_schema(self, error_schema: dict[str, Any]) -> None:
        body = _emitted_frames()["error"]["error"]

        assert set(body) <= set(error_schema["properties"])
        assert set(error_schema["required"]) <= set(body)


class TestClientMessages:
    def test_every_declared_type_decodes(self, client_schema: dict[str, Any]) -> None:
        """The reverse direction: the schema cannot promise a type the server refuses."""
        samples = {
            "subscribe": '{"type":"subscribe","topics":["snapshots:NIFTY"]}',
            "unsubscribe": '{"type":"unsubscribe","topics":["snapshots:NIFTY"]}',
            "ping": '{"type":"ping"}',
        }

        assert set(samples) == set(_variants(client_schema))
        for raw in samples.values():
            protocol.decode_client_message(raw)

    def test_the_declared_topic_pattern_accepts_what_the_domain_accepts(
        self, client_schema: dict[str, Any]
    ) -> None:
        pattern = re.compile(client_schema["$defs"]["topic"]["pattern"])

        for example in client_schema["$defs"]["topic"]["examples"]:
            assert pattern.fullmatch(example), f"{example} fails its own pattern"
            # And the domain parser must agree with the published pattern.
            Topic.parse(example)

    def test_the_declared_pattern_rejects_what_the_domain_rejects(
        self, client_schema: dict[str, Any]
    ) -> None:
        pattern = re.compile(client_schema["$defs"]["topic"]["pattern"])

        for bad in ("snapshots:nifty", "quotes:NIFTY", "snapshots:", "snapshots"):
            assert not pattern.fullmatch(bad), f"{bad} should not match"
