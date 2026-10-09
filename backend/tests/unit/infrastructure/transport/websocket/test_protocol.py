"""The wire codec.

Decoding is the server's attack surface — every frame here arrives from a
browser — so the refusals get as much attention as the happy path.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from chartnexus.infrastructure.transport.websocket import protocol

SERVER_TIME = datetime(2026, 10, 9, 8, 30, 15, tzinfo=UTC)


class TestDecoding:
    def test_decodes_a_subscribe(self) -> None:
        message = protocol.decode_client_message(
            '{"type":"subscribe","topics":["snapshots:NIFTY"],"id":"abc"}'
        )

        assert isinstance(message, protocol.Subscribe)
        assert message.topics == ("snapshots:NIFTY",)
        assert message.correlation_id == "abc"

    def test_decodes_an_unsubscribe(self) -> None:
        message = protocol.decode_client_message('{"type":"unsubscribe","topics":["snapshots:*"]}')

        assert isinstance(message, protocol.Unsubscribe)
        assert message.correlation_id is None

    def test_decodes_a_ping(self) -> None:
        assert isinstance(protocol.decode_client_message('{"type":"ping"}'), protocol.Ping)

    def test_accepts_bytes_as_well_as_text(self) -> None:
        assert isinstance(protocol.decode_client_message(b'{"type":"ping"}'), protocol.Ping)

    def test_de_duplicates_topics_rather_than_refusing_them(self) -> None:
        """A client resending its full set after a reconnect is encouraged."""
        message = protocol.decode_client_message(
            '{"type":"subscribe","topics":["snapshots:NIFTY","snapshots:NIFTY"]}'
        )

        assert message.topics == ("snapshots:NIFTY",)

    def test_does_not_validate_topic_grammar(self) -> None:
        """Shape only — the grammar belongs to the domain, in one place.

        A second copy of the rule here is how the two would drift.
        """
        message = protocol.decode_client_message('{"type":"subscribe","topics":["utter nonsense"]}')

        assert message.topics == ("utter nonsense",)

    @pytest.mark.parametrize(
        ("raw", "code"),
        [
            ("not json at all", protocol.MALFORMED_FRAME),
            ('["a","list"]', protocol.MALFORMED_FRAME),
            ('"a string"', protocol.MALFORMED_FRAME),
            ('{"type":"explode"}', protocol.UNKNOWN_MESSAGE_TYPE),
            ('{"topics":["snapshots:NIFTY"]}', protocol.UNKNOWN_MESSAGE_TYPE),
            ('{"type":"subscribe"}', protocol.MALFORMED_FRAME),
            ('{"type":"subscribe","topics":[]}', protocol.MALFORMED_FRAME),
            ('{"type":"subscribe","topics":"snapshots:NIFTY"}', protocol.MALFORMED_FRAME),
            ('{"type":"subscribe","topics":[1,2]}', protocol.MALFORMED_FRAME),
            ('{"type":"subscribe","topics":[""]}', protocol.MALFORMED_FRAME),
            ('{"type":"ping","id":""}', protocol.MALFORMED_FRAME),
            ('{"type":"ping","id":123}', protocol.MALFORMED_FRAME),
        ],
    )
    def test_refuses_with_the_right_code(self, raw: str, code: str) -> None:
        with pytest.raises(protocol.ProtocolError) as caught:
            protocol.decode_client_message(raw)

        assert caught.value.code == code

    def test_refuses_an_oversized_frame(self) -> None:
        """Before parsing, so a huge body is never handed to json.loads."""
        topics = ",".join(f'"snapshots:SYM{index}"' for index in range(2000))

        with pytest.raises(protocol.ProtocolError) as caught:
            protocol.decode_client_message('{"type":"subscribe","topics":[' + topics + "]}")

        assert caught.value.code == protocol.MALFORMED_FRAME

    def test_refuses_too_many_topics_in_one_message(self) -> None:
        topics = ",".join(f'"snapshots:S{index}"' for index in range(65))

        with pytest.raises(protocol.ProtocolError) as caught:
            protocol.decode_client_message('{"type":"subscribe","topics":[' + topics + "]}")

        assert caught.value.code == protocol.TOPIC_LIMIT_EXCEEDED

    def test_an_overlong_correlation_id_is_refused(self) -> None:
        with pytest.raises(protocol.ProtocolError):
            protocol.decode_client_message(json.dumps({"type": "ping", "id": "x" * 65}))

    def test_correlation_id_survives_into_the_error(self) -> None:
        """So a client can tie a refusal to the request that caused it."""
        with pytest.raises(protocol.ProtocolError) as caught:
            protocol.decode_client_message('{"type":"subscribe","topics":[],"id":"req-7"}')

        assert caught.value.correlation_id == "req-7"


class TestEncoding:
    def test_welcome_announces_the_protocol_version(self) -> None:
        body = json.loads(protocol.welcome(connection_id="abc123", server_time=SERVER_TIME))

        assert body == {
            "type": "welcome",
            "connection_id": "abc123",
            "protocol_version": protocol.PROTOCOL_VERSION,
            "server_time": "2026-10-09T08:30:15Z",
        }

    def test_timestamps_end_in_z_not_an_offset(self) -> None:
        """One shape on the wire; isoformat would render UTC as +00:00."""
        assert "+00:00" not in protocol.pong(server_time=SERVER_TIME)

    def test_ack_reports_the_whole_set_sorted(self) -> None:
        body = json.loads(protocol.ack(topics=("snapshots:NIFTY", "snapshots:BANKNIFTY")))

        assert body["topics"] == ["snapshots:BANKNIFTY", "snapshots:NIFTY"]

    def test_ack_omits_the_id_when_there_was_none(self) -> None:
        assert "id" not in json.loads(protocol.ack(topics=()))

    def test_snapshot_frame_carries_the_header_only(self) -> None:
        body = json.loads(
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
        )

        assert body["type"] == "snapshot_committed"
        assert body["topic"] == "snapshots:NIFTY"
        assert body["payload"]["spot"] == "24500.50"
        # No chain. The browser refetches detail over REST.
        assert "rows" not in body["payload"]

    def test_nullable_payload_fields_are_present_as_null(self) -> None:
        """Explicit null, not absent: the client reads one shape either way."""
        payload = json.loads(
            protocol.snapshot_committed(
                topic="snapshots:NIFTY",
                published_at="2026-10-09T08:30:15Z",
                payload=protocol.SnapshotPayload(
                    symbol="NIFTY",
                    session_date="2026-10-09",
                    captured_at="2026-10-09T08:30:00Z",
                    source="live",
                ),
            )
        )["payload"]

        assert payload["spot"] is None
        assert payload["expiry"] is None

    def test_error_nests_under_an_error_key(self) -> None:
        body = json.loads(
            protocol.error(code=protocol.UNKNOWN_TOPIC, message="Nope.", correlation_id="req-1")
        )

        assert body == {
            "type": "error",
            "error": {"code": protocol.UNKNOWN_TOPIC, "message": "Nope.", "id": "req-1"},
        }
