"""Bridge for the API monitor context.

The one module that context imports from infrastructure. It reads the Redis
counters written by the capture transport, the broker quota counters the
adapters already keep, and - for access - the user's role and their own
broker connections from Postgres.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from chartnexus.contexts.api_monitor.application.get_usage import GetApiUsage
from chartnexus.contexts.api_monitor.application.ports import (
    AdminEntry,
    MetricSample,
    QuotaUsage,
    RecentCall,
    Resolution,
)
from chartnexus.contexts.broker_connections.domain.value_objects import BrokerName
from chartnexus.contexts.identity.domain.value_objects import Role, UserStatus
from chartnexus.infrastructure.cache.redis.client import RedisClient
from chartnexus.infrastructure.observability.api_monitor.classify import app_fingerprint
from chartnexus.infrastructure.observability.api_monitor.schema import (
    RECENT_LIMIT,
    hour_key,
    minute_key,
    parse_field,
    recent_key,
)
from chartnexus.infrastructure.persistence.postgresql.repositories.identity.user_repository import (
    SqlAlchemyUserRepository,
)
from chartnexus.infrastructure.persistence.postgresql.repositories.integration.broker_connection_repository import (
    SqlAlchemyBrokerConnectionRepository,
)
from chartnexus.infrastructure.security.admin_audit import RedisAdminAuditTrail
from chartnexus.shared_kernel.types.identifiers import TenantId, UserId

_SCAN_COUNT = 200
_MASK_VISIBLE = 4


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def mask(app_id: str) -> str:
    return "..." + app_id[-_MASK_VISIBLE:] if len(app_id) > _MASK_VISIBLE else "...."


class RedisUsageSource:
    def __init__(self, redis: RedisClient, *, kite_daily: int, fyers_daily: int) -> None:
        self._redis = redis
        self._kite_daily = kite_daily
        self._fyers_daily = fyers_daily

    async def samples(
        self, start_epoch: int, end_epoch: int, resolution: Resolution
    ) -> list[MetricSample]:
        prefix = self._redis.key_prefix
        span = 60 if resolution == "minute" else 3600
        numbers = range(start_epoch // span, end_epoch // span + 1)
        key_for = minute_key if resolution == "minute" else hour_key
        pipeline = self._redis.client.pipeline(transaction=False)
        for number in numbers:
            pipeline.hgetall(key_for(prefix, number))
        results = await pipeline.execute()

        samples: list[MetricSample] = []
        for number, values in zip(numbers, results, strict=True):
            if not values:
                continue
            at = number * span
            for raw_field, raw_value in values.items():
                parsed = parse_field(_text(raw_field))
                if parsed is None:
                    continue
                series, metric = parsed
                try:
                    value = int(raw_value)
                except ValueError:
                    continue
                samples.append(
                    MetricSample(
                        at=at,
                        provider=series.provider,
                        endpoint=series.endpoint,
                        origin=series.origin,
                        app=series.app,
                        metric=metric,
                        value=value,
                    )
                )
        return samples

    async def recent(self, limit: int) -> list[RecentCall]:
        count = max(1, min(limit, RECENT_LIMIT))
        raw: list[bytes] = await self._redis.client.lrange(  # type: ignore[misc]
            recent_key(self._redis.key_prefix), 0, count - 1
        )
        calls: list[RecentCall] = []
        for item in raw:
            try:
                entry = json.loads(item)
                calls.append(
                    RecentCall(
                        at_ms=int(entry["t"]),
                        provider=str(entry["p"]),
                        endpoint=str(entry["e"]),
                        origin=str(entry["o"]),
                        app=str(entry["a"]),
                        method=str(entry["m"]),
                        status=entry.get("s"),
                        error=entry.get("x"),
                        elapsed_ms=int(entry["ms"]),
                    )
                )
            except (ValueError, KeyError, TypeError):
                continue
        return calls

    async def quotas(self) -> list[QuotaUsage]:
        """Today's broker quota counters, read where the adapters keep them.

        Kite: ``broker:quota:kite:<api key>:day:<YYYYMMDD>`` (calendar day).
        FYERS: ``broker:quota:<app id>:d`` (24 hours from the first call).
        """
        prefix = self._redis.key("broker", "quota")
        today = time.strftime("%Y%m%d")
        found: list[QuotaUsage] = []

        kite_pattern = f"{prefix}:kite:*:day:{today}"
        async for raw_key in self._redis.client.scan_iter(match=kite_pattern, count=_SCAN_COUNT):
            key = _text(raw_key)
            app_id = key[len(f"{prefix}:kite:") : -len(f":day:{today}")]
            found.append(await self._usage(key, "kite", app_id, self._kite_daily, "calendar day"))

        async for raw_key in self._redis.client.scan_iter(match=f"{prefix}:*:d", count=_SCAN_COUNT):
            key = _text(raw_key)
            app_id = key[len(prefix) + 1 : -len(":d")]
            if ":" in app_id:  # some other counter's key, not FYERS's
                continue
            found.append(
                await self._usage(key, "fyers", app_id, self._fyers_daily, "24 h from first call")
            )
        found.sort(key=lambda quota: (quota.broker, quota.app_label))
        return found

    async def _usage(
        self, key: str, broker: str, app_id: str, limit: int, window: str
    ) -> QuotaUsage:
        raw = await self._redis.client.get(key)
        try:
            used = int(raw) if raw is not None else 0
        except ValueError:
            used = 0
        return QuotaUsage(
            broker=broker,
            app=app_fingerprint(app_id),
            app_label=mask(app_id),
            used_today=used,
            daily_limit=limit,
            window=window,
        )


class DatabaseAccessGate:
    def __init__(self, container: Any) -> None:
        self._container = container

    async def is_admin(self, user_id: UserId) -> bool:
        async with self._container.database.read_session() as session:
            user = await SqlAlchemyUserRepository(session).get(user_id)
        return user is not None and user.status is UserStatus.ACTIVE and user.has_role(Role.ADMIN)

    async def own_apps(self, tenant_id: TenantId) -> frozenset[str]:
        apps: set[str] = set()
        async with self._container.database.read_session() as session:
            repository = SqlAlchemyBrokerConnectionRepository(session, self._container.token_cipher)
            for broker in BrokerName:
                connection = await repository.find(tenant_id, broker)
                if connection is not None and connection.credentials is not None:
                    apps.add(app_fingerprint(connection.credentials.app_id))
        return frozenset(apps)


class AdminRosterReader:
    def __init__(self, container: Any) -> None:
        self._container = container

    async def admins(self) -> list[AdminEntry]:
        async with self._container.database.read_session() as session:
            users = await SqlAlchemyUserRepository(session).list_with_role(Role.ADMIN.value)
        return [
            AdminEntry(email=user.email.value, since=user.updated_at.date().isoformat())
            for user in users
        ]

    async def audit(self, limit: int) -> list[dict[str, str]]:
        entries = await RedisAdminAuditTrail(self._container.redis).recent(limit)
        return [{key: str(value) for key, value in entry.items()} for entry in entries]


@dataclass(frozen=True, slots=True)
class ApiMonitorServices:
    usage: GetApiUsage
    gate: DatabaseAccessGate
    roster: AdminRosterReader
    max_admins: int


def build_api_monitor(container: Any) -> ApiMonitorServices:
    settings = container.settings
    source = RedisUsageSource(
        container.redis,
        kite_daily=settings.kite.requests_per_day,
        fyers_daily=settings.broker.quota_requests_per_day,
    )
    return ApiMonitorServices(
        usage=GetApiUsage(source, clock=time.time),
        gate=DatabaseAccessGate(container),
        roster=AdminRosterReader(container),
        max_admins=settings.auth.admin_max_count,
    )
