"""The capture half of the API monitor.

What matters most here is what is *not* stored: no query string, no token, no
Telegram bot secret. And the monitor must never change the call it measures -
the same response or exception has to reach the caller.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import httpx
import pytest

from chartnexus.infrastructure.observability.api_monitor.classify import (
    NO_APP,
    app_fingerprint,
    app_from_authorization,
    endpoint_template,
    provider_for,
)
from chartnexus.infrastructure.observability.api_monitor.origin import (
    api_call_origin,
    current_origin,
)
from chartnexus.infrastructure.observability.api_monitor.recorder import ApiCallRecorder
from chartnexus.infrastructure.observability.api_monitor.schema import (
    bucket_index,
    parse_field,
)
from chartnexus.infrastructure.observability.api_monitor.transport import MonitoredTransport

SECRET_TOKEN = "s3cr3t-access-token-value"
BOT_TOKEN = "123456:AAH-very-secret-bot-token"


class _Pipeline:
    def __init__(self, store: _FakeRedis) -> None:
        self._store = store
        self._ops: list[tuple[str, tuple[Any, ...]]] = []

    def hincrby(self, key: str, name: str, amount: int) -> None:
        self._ops.append(("hincrby", (key, name, amount)))

    def expire(self, key: str, ttl: int) -> None:
        self._ops.append(("expire", (key, ttl)))

    def lpush(self, key: str, *values: str) -> None:
        self._ops.append(("lpush", (key, *values)))

    def ltrim(self, key: str, start: int, end: int) -> None:
        self._ops.append(("ltrim", (key, start, end)))

    async def execute(self) -> list[Any]:
        if self._store.down:
            raise ConnectionError("redis is down")
        for name, args in self._ops:
            if name == "hincrby":
                key, field, amount = args
                self._store.hashes[key][field] += amount
            elif name == "expire":
                self._store.ttls[args[0]] = args[1]
            elif name == "lpush":
                key, *values = args
                for value in values:
                    self._store.lists[key].insert(0, value)
            elif name == "ltrim":
                key, start, end = args
                self._store.lists[key] = self._store.lists[key][start : end + 1]
        return []


class _FakeRedis:
    key_prefix = "cn"

    def __init__(self) -> None:
        self.hashes: defaultdict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.lists: defaultdict[str, list[str]] = defaultdict(list)
        self.ttls: dict[str, int] = {}
        self.down = False

    @property
    def client(self) -> _FakeRedis:
        return self

    def pipeline(self, transaction: bool = True) -> _Pipeline:
        return _Pipeline(self)

    def everything(self) -> str:
        """Every stored key, field and value as one string, for leak checks."""
        parts = [*self.hashes, *self.lists]
        for fields in self.hashes.values():
            parts.extend(fields)
        for values in self.lists.values():
            parts.extend(values)
        return "\n".join(parts)


def _client(recorder: ApiCallRecorder, handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=MonitoredTransport(httpx.MockTransport(handler), recorder))


class TestClassify:
    @pytest.mark.parametrize(
        ("host", "provider"),
        [
            ("api.kite.trade", "kite"),
            ("api-t1.fyers.in", "fyers"),
            ("www.nseindia.com", "nse"),
            ("query1.finance.yahoo.com", "yahoo"),
            ("api.telegram.org", "telegram"),
            ("api.callmebot.com", "whatsapp"),
            ("oauth2.googleapis.com", "google"),
            ("example.org", "other"),
            ("notkite.trade.evil.com", "other"),
        ],
    )
    def test_providers(self, host: str, provider: str) -> None:
        assert provider_for(host) == provider

    def test_ids_and_intervals_are_templated(self) -> None:
        assert (
            endpoint_template("/instruments/historical/256265/minute")
            == "/instruments/historical/{id}/{interval}"
        )
        assert endpoint_template("/quote") == "/quote"

    def test_a_telegram_bot_token_never_survives(self) -> None:
        assert endpoint_template(f"/bot{BOT_TOKEN}/sendMessage") == "/bot{token}/sendMessage"

    def test_kite_and_fyers_app_ids_are_fingerprinted_and_the_token_ignored(self) -> None:
        kite = app_from_authorization("kite", f"token myapikey:{SECRET_TOKEN}")
        fyers = app_from_authorization("fyers", f"ABCDE123XY-100:{SECRET_TOKEN}")
        assert kite == app_fingerprint("myapikey")
        assert fyers == app_fingerprint("ABCDE123XY-100")
        assert SECRET_TOKEN not in kite + fyers
        assert len(kite) == 12

    def test_non_broker_headers_are_never_read(self) -> None:
        assert app_from_authorization("telegram", "Bearer abc:def") == NO_APP
        assert app_from_authorization("kite", None) == NO_APP
        assert app_from_authorization("kite", "garbage") == NO_APP

    def test_buckets(self) -> None:
        assert bucket_index(10) == 0
        assert bucket_index(50) == 0
        assert bucket_index(51) == 1
        assert bucket_index(99_999) == 11

    def test_origin_falls_back_and_nests(self) -> None:
        outer = current_origin()
        with api_call_origin("ingest-capture-loop"):
            assert current_origin() == "ingest-capture"
            with api_call_origin("a|b"):
                assert current_origin() == "a/b"
        assert current_origin() == outer


class TestTransportAndRecorder:
    async def test_a_call_is_counted_without_its_query_or_token(self) -> None:
        redis = _FakeRedis()
        recorder = ApiCallRecorder(redis, flush_interval=3600)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "success"})

        async with _client(recorder, handler) as client:
            with api_call_origin("ingest"):
                response = await client.get(
                    "https://api.kite.trade/quote",
                    params={"i": "NSE:INFY", "apikey": "query-secret"},
                    headers={"Authorization": f"token myapikey:{SECRET_TOKEN}"},
                )
            await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage?chat_id=42")
        assert response.status_code == 200
        await recorder.aclose()

        stored = redis.everything()
        for secret in (SECRET_TOKEN, "query-secret", BOT_TOKEN, "chat_id", "NSE:INFY", "myapikey"):
            assert secret not in stored

        minute = next(key for key in redis.hashes if ":apimon:m:" in key)
        fields = {parse_field(name): value for name, value in redis.hashes[minute].items()}
        counts = {key[0].provider: value for key, value in fields.items() if key and key[1] == "n"}
        assert counts == {"kite": 1, "telegram": 1}
        kite_series = next(key[0] for key in fields if key and key[0].provider == "kite")
        assert kite_series.endpoint == "/quote"
        assert kite_series.origin == "ingest"
        assert kite_series.app == app_fingerprint("myapikey")
        assert any(":apimon:h:" in key for key in redis.hashes)
        recent = [json.loads(item) for item in redis.lists["cn:apimon:recent"]]
        assert [entry["p"] for entry in recent] == ["telegram", "kite"]  # newest first

    async def test_errors_are_counted_and_still_reach_the_caller(self) -> None:
        redis = _FakeRedis()
        recorder = ApiCallRecorder(redis, flush_interval=3600)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/slow":
                raise httpx.ReadTimeout("too slow", request=request)
            return httpx.Response(503 if request.url.path == "/down" else 429)

        async with _client(recorder, handler) as client:
            assert (await client.get("https://api.kite.trade/down")).status_code == 503
            assert (await client.get("https://api.kite.trade/busy")).status_code == 429
            with pytest.raises(httpx.ReadTimeout):
                await client.get("https://api.kite.trade/slow")
        await recorder.aclose()

        minute = next(key for key in redis.hashes if ":apimon:m:" in key)
        errors = {
            parsed[1]: value
            for name, value in redis.hashes[minute].items()
            if (parsed := parse_field(name)) and parsed[1].startswith("e:")
        }
        assert errors == {"e:http_5xx": 1, "e:http_429": 1, "e:timeout": 1}

    async def test_redis_being_down_never_breaks_a_call(self) -> None:
        redis = _FakeRedis()
        redis.down = True
        recorder = ApiCallRecorder(redis, flush_interval=3600)

        async with _client(recorder, lambda _request: httpx.Response(200)) as client:
            assert (await client.get("https://api.fyers.in/data/quotes")).status_code == 200
        await recorder.aclose()  # flush fails quietly
        assert redis.hashes == {}

    async def test_disabled_monitor_records_nothing(self) -> None:
        redis = _FakeRedis()
        recorder = ApiCallRecorder(redis, enabled=False)
        async with _client(recorder, lambda _request: httpx.Response(200)) as client:
            await client.get("https://api.kite.trade/quote")
        await recorder.aclose()
        assert redis.everything() == ""
