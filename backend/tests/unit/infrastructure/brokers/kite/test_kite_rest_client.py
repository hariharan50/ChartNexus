"""The Kite HTTP contract: checksum, login URL, headers and the error envelope.

Fixtures under ``tests/fixtures/kite`` follow the shapes in Kite Connect v3's
documentation. They still need checking against a live account (ADR 0002).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
import pytest

from chartnexus.contexts.broker_connections.domain.errors import (
    BrokerRejectedError,
    BrokerUnavailableError,
)
from chartnexus.infrastructure.brokers.kite.rest_client import (
    QUOTE_BATCH_LIMIT,
    KiteRestClient,
    authorization_header,
    batch_instruments,
    checksum,
)

pytestmark = pytest.mark.unit

IST = ZoneInfo("Asia/Kolkata")

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "kite"


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _client(handler: Any) -> tuple[KiteRestClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return KiteRestClient(http), seen


def _reply(status: int, body: Any) -> Any:
    return lambda _request: httpx.Response(status, json=body)


class TestChecksum:
    def test_it_is_sha256_of_the_three_parts_with_no_separator(self) -> None:
        expected = hashlib.sha256(b"abc123reqTOKENs3cret").hexdigest()
        assert checksum("abc123", "reqTOKEN", "s3cret") == expected

    def test_a_known_vector(self) -> None:
        # sha256("keytokensecret"), computed outside the code under test.
        assert checksum("key", "token", "secret") == (
            "08a03d928417ea4085557933d3b187ff2a3515b039d6054dbd230c95d978a17a"
        )

    def test_the_authorization_header_shape(self) -> None:
        assert authorization_header("abc123", "tok") == "token abc123:tok"


class TestLoginUrl:
    def test_state_rides_in_redirect_params(self) -> None:
        client, _ = _client(_reply(200, {}))
        url = client.build_login_url(api_key="abc123", state="s/t+a=te")

        query = parse_qs(urlparse(url).query)
        assert query["v"] == ["3"]
        assert query["api_key"] == ["abc123"]
        # Kite decodes redirect_params once and appends it to the registered
        # redirect URL, so state must survive as its own encoded parameter.
        assert parse_qs(query["redirect_params"][0]) == {"state": ["s/t+a=te"]}

    def test_it_is_percent_encoded_in_the_url(self) -> None:
        client, _ = _client(_reply(200, {}))
        url = client.build_login_url(api_key="abc123", state="xyz")
        assert "redirect_params=state%3Dxyz" in url


class TestSession:
    async def test_create_session_posts_the_checksum_not_the_secret(self) -> None:
        client, seen = _client(_reply(200, _fixture("session.json")))

        payload = await client.create_session(
            api_key="abc123", api_secret="s3cretvalue", request_token="rt"
        )

        assert payload["data"]["access_token"] == "acc3ss-t0ken"
        request = seen[0]
        assert request.method == "POST"
        assert request.url.path == "/session/token"
        form = parse_qs(request.content.decode())
        assert form["checksum"] == [checksum("abc123", "rt", "s3cretvalue")]
        assert "s3cretvalue" not in request.content.decode()
        assert request.headers["X-Kite-Version"] == "3"

    async def test_authenticated_calls_carry_the_token_header(self) -> None:
        client, seen = _client(_reply(200, _fixture("profile.json")))
        await client.fetch_profile(api_key="abc123", access_token="tok")
        assert seen[0].headers["Authorization"] == "token abc123:tok"

    async def test_invalidate_sends_a_delete(self) -> None:
        client, seen = _client(_reply(200, {"status": "success", "data": True}))
        await client.invalidate_session(api_key="abc123", access_token="tok")
        assert seen[0].method == "DELETE"
        assert seen[0].url.path == "/session/token"


class TestEnvelope:
    async def test_a_token_exception_is_a_rejection(self) -> None:
        client, _ = _client(_reply(403, _fixture("error_token.json")))
        with pytest.raises(BrokerRejectedError, match="rejected this session"):
            await client.fetch_profile(api_key="k", access_token="t")

    async def test_a_token_exception_is_a_rejection_even_on_200(self) -> None:
        body = {**_fixture("error_token.json")}
        client, _ = _client(_reply(200, body))
        with pytest.raises(BrokerRejectedError):
            await client.fetch_profile(api_key="k", access_token="t")

    async def test_an_input_exception_carries_the_message(self) -> None:
        client, _ = _client(_reply(400, _fixture("error_input.json")))
        with pytest.raises(BrokerRejectedError, match="Invalid `from` date"):
            await client.fetch_profile(api_key="k", access_token="t")

    async def test_a_long_message_is_truncated(self) -> None:
        body = {"status": "error", "message": "x" * 500, "error_type": "InputException"}
        client, _ = _client(_reply(400, body))
        with pytest.raises(BrokerRejectedError) as raised:
            await client.fetch_profile(api_key="k", access_token="t")
        assert "x" * 201 not in str(raised.value)

    @pytest.mark.parametrize("status", [429, 500, 502, 503])
    async def test_throttling_and_server_errors_are_transient(self, status: int) -> None:
        client, _ = _client(_reply(status, {"status": "error"}))
        with pytest.raises(BrokerUnavailableError):
            await client.fetch_profile(api_key="k", access_token="t")

    async def test_a_network_exception_is_transient(self) -> None:
        client, _ = _client(_reply(502, _fixture("error_network.json")))
        with pytest.raises(BrokerUnavailableError):
            await client.fetch_profile(api_key="k", access_token="t")

    async def test_a_network_exception_with_a_4xx_is_still_transient(self) -> None:
        client, _ = _client(_reply(400, _fixture("error_network.json")))
        with pytest.raises(BrokerUnavailableError):
            await client.fetch_profile(api_key="k", access_token="t")

    async def test_a_transport_failure_is_transient(self) -> None:
        def explode(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("slow", request=request)

        client, _ = _client(explode)
        with pytest.raises(BrokerUnavailableError):
            await client.fetch_profile(api_key="k", access_token="t")

    async def test_html_instead_of_json_is_a_rejection(self) -> None:
        client, _ = _client(lambda _request: httpx.Response(200, text="<html>"))
        with pytest.raises(BrokerRejectedError, match="unreadable"):
            await client.fetch_profile(api_key="k", access_token="t")


class TestMarketData:
    async def test_quotes_are_requested_as_repeated_i_params(self) -> None:
        client, seen = _client(_reply(200, {"status": "success", "data": {"NSE:INFY": {}}}))
        data = await client.fetch_quotes(
            api_key="k", access_token="t", instruments=["NSE:INFY", "NSE:NIFTY 50"]
        )
        assert data == {"NSE:INFY": {}}
        assert seen[0].url.params.get_list("i") == ["NSE:INFY", "NSE:NIFTY 50"]

    async def test_more_than_the_batch_limit_is_refused_locally(self) -> None:
        client, seen = _client(_reply(200, {}))
        with pytest.raises(ValueError, match="at most"):
            await client.fetch_quotes(
                api_key="k",
                access_token="t",
                instruments=[f"NFO:X{i}" for i in range(QUOTE_BATCH_LIMIT + 1)],
            )
        assert seen == []

    async def test_historical_candles_and_window(self) -> None:
        client, seen = _client(_reply(200, _fixture("historical_day.json")))
        candles = await client.fetch_historical(
            api_key="k",
            access_token="t",
            instrument_token=256265,
            interval="day",
            start=datetime(2026, 7, 1, 9, 15, tzinfo=IST),
            end=datetime(2026, 8, 1, 15, 30, tzinfo=IST),
        )
        assert len(candles) == 3
        request = seen[0]
        assert request.url.path == "/instruments/historical/256265/day"
        assert request.url.params["from"] == "2026-07-01 09:15:00"
        assert request.url.params["to"] == "2026-08-01 15:30:00"


class TestBatching:
    def test_batches_are_deduplicated_and_bounded(self) -> None:
        keys = [f"NFO:X{i}" for i in range(1200)] + ["NFO:X0"]
        batches = batch_instruments(keys)
        assert [len(b) for b in batches] == [500, 500, 200]
        assert [key for batch in batches for key in batch] == list(dict.fromkeys(keys))

    def test_a_zero_batch_size_is_a_programming_error(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            batch_instruments(["a"], size=0)
