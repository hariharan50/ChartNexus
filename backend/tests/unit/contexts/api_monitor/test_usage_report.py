"""The read half: percentile maths, report building, and per-user filtering."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from chartnexus.contexts.api_monitor.api import router as routes
from chartnexus.contexts.api_monitor.application.get_usage import GetApiUsage, UsageFilters
from chartnexus.contexts.api_monitor.application.ports import (
    MetricSample,
    QuotaUsage,
    RecentCall,
)
from chartnexus.contexts.api_monitor.domain.stats import (
    CallStats,
    health_of,
    percentile_from_buckets,
)
from chartnexus.shared_kernel.domain.errors import AuthorizationError

NOW = 1_800_000_000  # a fixed epoch second
MINE, THEIRS = "aaaaaaaaaaaa", "bbbbbbbbbbbb"


def _samples(app: str, *, calls: int, slow: bool, provider: str = "kite") -> list[MetricSample]:
    at = NOW - 120
    bucket = "b8" if slow else "b1"  # 1.5-2.5 s vs 50-100 ms
    base = {"at": at, "provider": provider, "endpoint": "/quote", "origin": "ingest", "app": app}
    return [
        MetricSample(**base, metric="n", value=calls),
        MetricSample(**base, metric="ms", value=calls * (2000 if slow else 80)),
        MetricSample(**base, metric=bucket, value=calls),
        MetricSample(**base, metric="e:http_5xx", value=1),
    ]


def _shift(sample: MetricSample) -> MetricSample:
    return MetricSample(
        at=sample.at - 3600,
        provider=sample.provider,
        endpoint=sample.endpoint,
        origin=sample.origin,
        app=sample.app,
        metric=sample.metric,
        value=sample.value // 2,
    )


class _Source:
    def __init__(self) -> None:
        self.data = _samples(MINE, calls=10, slow=False) + _samples(THEIRS, calls=90, slow=True)

    async def samples(self, start: int, end: int, resolution: str) -> list[MetricSample]:
        assert resolution == "minute"
        # Only the current hour holds data; the previous-period read gets the
        # same calls an hour earlier, at half the volume.
        if end >= NOW - 60:
            return self.data
        return [_shift(sample) for sample in self.data]

    async def recent(self, limit: int) -> list[RecentCall]:
        return [
            RecentCall(NOW * 1000, "kite", "/quote", "ingest", app, "GET", 200, None, 80)
            for app in (MINE, THEIRS)
        ]

    async def quotas(self) -> list[QuotaUsage]:
        return [
            QuotaUsage("kite", MINE, "...AB12", 10, 200_000, "calendar day"),
            QuotaUsage("kite", THEIRS, "...CD34", 90, 200_000, "calendar day"),
        ]


class TestPercentiles:
    def test_empty_is_unknown(self) -> None:
        assert percentile_from_buckets([0] * 12, 0.95) is None

    def test_interpolates_inside_the_bucket(self) -> None:
        buckets = [0] * 12
        buckets[1] = 100  # all between 50 and 100 ms
        assert percentile_from_buckets(buckets, 0.5) == pytest.approx(75.0)

    def test_the_open_top_bucket_reports_its_floor(self) -> None:
        buckets = [0] * 12
        buckets[11] = 5
        assert percentile_from_buckets(buckets, 0.99) == 10_000.0

    def test_stats_merge(self) -> None:
        one, two = CallStats(), CallStats()
        one.add_metric("n", 2)
        one.add_metric("e:timeout", 1)
        two.add_metric("n", 3)
        one.merge(two)
        assert one.calls == 5
        assert one.error_rate == pytest.approx(0.2)


class TestHealth:
    def _stats(self, calls: int, **errors: int) -> CallStats:
        stats = CallStats()
        stats.add_metric("n", calls)
        stats.add_metric("b1", calls)
        for name, count in errors.items():
            stats.add_metric(f"e:{name}", count)
        return stats

    def test_rejections_do_not_make_a_provider_unhealthy(self) -> None:
        # An expired Kite token answers 403 to everything: Kite is fine.
        assert health_of(self._stats(10, http_4xx=10)) == "healthy"

    def test_timeouts_and_server_errors_do(self) -> None:
        assert health_of(self._stats(10, timeout=6)) == "down"
        assert health_of(self._stats(100, http_5xx=6)) == "degraded"
        assert health_of(self._stats(0)) == "idle"


class TestReport:
    async def test_the_admin_report_sees_every_app(self) -> None:
        report = await GetApiUsage(_Source(), clock=lambda: NOW).report("1h", apps=None)
        assert report.totals.calls == 100
        assert len(report.recent) == 2
        assert len(report.quotas) == 2
        assert len(report.series) == 61  # one point a minute, both ends included
        assert sum(point.stats.calls for point in report.series) == 100

    async def test_a_users_report_contains_only_their_own_app(self) -> None:
        report = await GetApiUsage(_Source(), clock=lambda: NOW).report(
            "1h", apps=frozenset({MINE})
        )
        assert report.totals.calls == 10
        assert report.totals.error_count == 1
        # Their p95 must not be dragged up by the other user's slow calls.
        assert report.totals.percentile(0.95) is not None
        assert report.totals.percentile(0.95) <= 100
        assert [call.app for call in report.recent] == [MINE]
        assert [quota.app_label for quota in report.quotas] == ["...AB12"]

    async def test_a_user_without_a_broker_sees_nothing(self) -> None:
        report = await GetApiUsage(_Source(), clock=lambda: NOW).report("1h", apps=frozenset())
        assert report.totals.calls == 0
        assert report.recent == []
        assert report.quotas == []

    async def test_health_rate_peak_and_previous_period(self) -> None:
        report = await GetApiUsage(_Source(), clock=lambda: NOW).report("1h", apps=None)
        (kite,) = report.health
        assert kite.provider == "kite"
        assert kite.status == "degraded"  # 90 calls at ~2 s push p95 past 2 s
        assert kite.peak_per_minute == 100
        assert report.peak_per_minute == 100
        assert report.calls_per_minute_now == pytest.approx(20.0)  # 100 calls / 5 min
        assert report.previous is not None
        assert report.previous.calls == 50
        assert report.provider_options == ["kite"]
        assert report.origin_options == ["ingest"]
        assert [row.key for row in report.apps] == [(THEIRS,), (MINE,)]

    async def test_filters_narrow_everything(self) -> None:
        source = _Source()
        source.data += _samples(MINE, calls=7, slow=False, provider="fyers")
        report = await GetApiUsage(source, clock=lambda: NOW).report(
            "1h", apps=None, filters=UsageFilters(provider="fyers")
        )
        assert report.totals.calls == 7
        assert [row.key for row in report.providers] == [("fyers",)]
        assert report.recent == []  # recent calls were all Kite
        assert report.quotas == []  # quota rows were all Kite
        assert report.provider_options == ["fyers", "kite"]  # options stay unfiltered

    async def test_unknown_range_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown range"):
            await GetApiUsage(_Source(), clock=lambda: NOW).report("30d", apps=None)


class TestRoutes:
    def _services(self, *, admin: bool) -> Any:
        async def is_admin(user_id: Any) -> bool:
            return admin

        async def own_apps(tenant_id: Any) -> frozenset[str]:
            return frozenset({MINE})

        return SimpleNamespace(
            gate=SimpleNamespace(is_admin=is_admin, own_apps=own_apps),
            usage=GetApiUsage(_Source(), clock=lambda: NOW),
        )

    def _principal(self) -> Any:
        return SimpleNamespace(user_id="u1", tenant_id="t1")

    async def test_a_non_admin_is_refused_the_platform_view(self) -> None:
        with pytest.raises(AuthorizationError):
            await routes.admin_overview(self._principal(), self._services(admin=False), range_="1h")

    async def test_route_filters_reach_the_report(self) -> None:
        response = await routes.admin_overview(
            self._principal(),
            self._services(admin=True),
            range_="1h",
            provider="kite",
            origin="ingest",
            endpoint="/quote",
        )
        assert response.filters.provider == "kite"
        assert response.totals.calls == 100
        assert len(response.totals.histogram) == 12

    async def test_an_admin_gets_the_platform_view(self) -> None:
        response = await routes.admin_overview(
            self._principal(), self._services(admin=True), range_="1h"
        )
        assert response.scope == "platform"
        assert response.totals.calls == 100

    async def test_mine_is_scoped_to_the_callers_app(self) -> None:
        response = await routes.my_usage(
            self._principal(), self._services(admin=False), range_="1h"
        )
        assert response.scope == "mine"
        assert response.totals.calls == 10
        assert "app" not in response.recent[0].model_dump()  # fingerprints never leave
