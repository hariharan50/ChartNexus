"""Turn stored counters into one usage report.

The admin overview and a user's own view are the same report over different
rows: ``apps=None`` keeps everything, a set of fingerprints keeps only calls
made with those broker apps. Filtering happens before anything is summed, so
another user's calls cannot leak into a total, a percentile or a time series.

The optional ``provider`` / ``origin`` / ``endpoint`` filters narrow the report
further, and are how the page drills into one endpoint: the drill-down is just
this report, filtered.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from chartnexus.contexts.api_monitor.application.ports import (
    MetricSample,
    QuotaUsage,
    RecentCall,
    Resolution,
    UsageSource,
)
from chartnexus.contexts.api_monitor.domain.stats import (
    HEALTH_WINDOW_SECONDS,
    CallStats,
    health_of,
)

UsageRange = Literal["1h", "6h", "24h", "7d"]

#: range -> (window seconds, stored resolution, chart step seconds)
_RANGES: dict[str, tuple[int, Resolution, int]] = {
    "1h": (3600, "minute", 60),
    "6h": (6 * 3600, "minute", 300),
    "24h": (24 * 3600, "minute", 900),
    "7d": (7 * 86_400, "hour", 3600),
}

#: Where the previous, equally long window can be read from. Minute buckets
#: live 25 hours and hourly ones 8 days, so a 7-day range has no previous week.
_PREVIOUS_RESOLUTION: dict[str, Resolution | None] = {
    "1h": "minute",
    "6h": "minute",
    "24h": "hour",
    "7d": None,
}

_MAX_ENDPOINT_ROWS = 100
_MAX_RECENT = 200
_RATE_WINDOW_SECONDS = 5 * 60
NO_APP = "-"


@dataclass(frozen=True, slots=True)
class UsageFilters:
    provider: str | None = None
    origin: str | None = None
    endpoint: str | None = None

    def keeps(self, provider: str, origin: str, endpoint: str) -> bool:
        return (
            (self.provider is None or provider == self.provider)
            and (self.origin is None or origin == self.origin)
            and (self.endpoint is None or endpoint == self.endpoint)
        )


@dataclass(slots=True)
class GroupRow:
    key: tuple[str, ...]
    stats: CallStats


@dataclass(slots=True)
class ProviderHealth:
    provider: str
    status: str  # idle | healthy | degraded | down
    recent: CallStats
    peak_per_minute: int | None
    last_call_ms: int | None
    last_error_ms: int | None
    last_error: str | None


@dataclass(slots=True)
class SeriesPoint:
    at: int
    by_provider: dict[str, int] = field(default_factory=dict)
    stats: CallStats = field(default_factory=CallStats)


@dataclass(slots=True)
class UsageReport:
    range: str
    step_seconds: int
    start: int
    end: int
    totals: CallStats
    providers: list[GroupRow]
    endpoints: list[GroupRow]
    origins: list[GroupRow]
    series: list[SeriesPoint]
    recent: list[RecentCall]
    quotas: list[QuotaUsage]
    filters: UsageFilters = field(default_factory=UsageFilters)
    previous: CallStats | None = None
    health: list[ProviderHealth] = field(default_factory=list)
    apps: list[GroupRow] = field(default_factory=list)
    calls_per_minute_now: float | None = None
    peak_per_minute: int | None = None
    provider_options: list[str] = field(default_factory=list)
    origin_options: list[str] = field(default_factory=list)


def range_window(name: str) -> tuple[int, Resolution, int]:
    if name not in _RANGES:
        msg = f"unknown range {name!r}"
        raise ValueError(msg)
    return _RANGES[name]


class GetApiUsage:
    def __init__(self, source: UsageSource, *, clock: Callable[[], float]) -> None:
        self._source = source
        self._clock = clock

    async def report(
        self,
        range_name: str,
        *,
        apps: frozenset[str] | None,
        filters: UsageFilters | None = None,
    ) -> UsageReport:
        window, resolution, step = range_window(range_name)
        filters = filters or UsageFilters()
        end = int(self._clock())
        start = end - window

        scoped = _scope(await self._source.samples(start, end, resolution), apps)
        provider_options = sorted({sample.provider for sample in scoped})
        origin_options = sorted({sample.origin for sample in scoped})
        samples = [s for s in scoped if filters.keeps(s.provider, s.origin, s.endpoint)]

        tally = _Tally(start=start, end=end, step=step, resolution=resolution)
        for sample in samples:
            tally.add(sample)

        recent = await self._source.recent(_MAX_RECENT * (5 if apps is not None else 3))
        if apps is not None:
            recent = [call for call in recent if call.app in apps]
        recent = [c for c in recent if filters.keeps(c.provider, c.origin, c.endpoint)]

        quotas = await self._source.quotas()
        if apps is not None:
            quotas = [quota for quota in quotas if quota.app in apps]
        if filters.provider is not None:
            quotas = [quota for quota in quotas if quota.broker == filters.provider]

        previous = await self._previous(range_name, start, window, apps, filters)

        return UsageReport(
            range=range_name,
            step_seconds=step,
            start=start,
            end=end,
            totals=tally.totals,
            providers=_rows(tally.providers),
            endpoints=_rows(tally.endpoints)[:_MAX_ENDPOINT_ROWS],
            origins=_rows(tally.origins),
            series=tally.series(),
            recent=recent[:_MAX_RECENT],
            quotas=quotas,
            filters=filters,
            previous=previous,
            health=_health(
                tally.providers, tally.recent_by_provider, tally.per_minute_by_provider, recent
            ),
            apps=_rows(tally.apps),
            calls_per_minute_now=tally.calls_per_minute_now(),
            peak_per_minute=max(tally.per_minute.values()) if tally.per_minute else None,
            provider_options=provider_options,
            origin_options=origin_options,
        )

    async def _previous(
        self,
        range_name: str,
        start: int,
        window: int,
        apps: frozenset[str] | None,
        filters: UsageFilters,
    ) -> CallStats | None:
        resolution = _PREVIOUS_RESOLUTION.get(range_name)
        if resolution is None:
            return None
        # Hourly buckets start on the hour; stop one bucket short so the
        # previous window never overlaps the current one.
        end = start - 1 if resolution == "minute" else start - 3600
        samples = _scope(await self._source.samples(start - window, end, resolution), apps)
        stats = CallStats()
        for sample in samples:
            if filters.keeps(sample.provider, sample.origin, sample.endpoint):
                stats.add_metric(sample.metric, sample.value)
        return stats


class _Tally:
    """Every running total the report needs, filled in one pass over the samples."""

    def __init__(self, *, start: int, end: int, step: int, resolution: Resolution) -> None:
        self.end = end
        self.step = step
        self.resolution = resolution
        self.first_point = start - start % step
        self.health_from = end - HEALTH_WINDOW_SECONDS
        self.rate_from = end - (_RATE_WINDOW_SECONDS if resolution == "minute" else 3600)
        self.totals = CallStats()
        self.providers: dict[tuple[str, ...], CallStats] = {}
        self.endpoints: dict[tuple[str, ...], CallStats] = {}
        self.origins: dict[tuple[str, ...], CallStats] = {}
        self.apps: dict[tuple[str, ...], CallStats] = {}
        self.recent_by_provider: dict[str, CallStats] = {}
        self.per_minute: dict[int, int] = {}
        self.per_minute_by_provider: dict[tuple[str, int], int] = {}
        self.points: dict[int, SeriesPoint] = {}
        self.rate_calls = 0

    def add(self, sample: MetricSample) -> None:
        metric, value = sample.metric, sample.value
        self.totals.add_metric(metric, value)
        _bucket(self.providers, (sample.provider,)).add_metric(metric, value)
        _bucket(self.endpoints, (sample.provider, sample.endpoint)).add_metric(metric, value)
        _bucket(self.origins, (sample.origin,)).add_metric(metric, value)
        if sample.app != NO_APP:
            _bucket(self.apps, (sample.app,)).add_metric(metric, value)
        recent_hour = self.resolution == "hour" and sample.at >= self.end - 3600
        if sample.at >= self.health_from or recent_hour:
            _bucket(self.recent_by_provider, sample.provider).add_metric(metric, value)

        at = max(self.first_point, sample.at - sample.at % self.step)
        point = self.points.get(at)
        if point is None:
            point = self.points[at] = SeriesPoint(at=at)
        point.stats.add_metric(metric, value)
        if metric != "n":
            return
        point.by_provider[sample.provider] = point.by_provider.get(sample.provider, 0) + value
        if sample.at >= self.rate_from:
            self.rate_calls += value
        if self.resolution == "minute":
            self.per_minute[sample.at] = self.per_minute.get(sample.at, 0) + value
            key = (sample.provider, sample.at)
            self.per_minute_by_provider[key] = self.per_minute_by_provider.get(key, 0) + value

    def series(self) -> list[SeriesPoint]:
        return [
            self.points.get(at) or SeriesPoint(at=at)
            for at in range(self.first_point, self.end + 1, self.step)
        ]

    def calls_per_minute_now(self) -> float:
        minutes = (_RATE_WINDOW_SECONDS if self.resolution == "minute" else 3600) / 60
        return self.rate_calls / minutes


def _scope(samples: list[MetricSample], apps: frozenset[str] | None) -> list[MetricSample]:
    if apps is None:
        return samples
    return [sample for sample in samples if sample.app in apps]


def _health(
    providers: dict[tuple[str, ...], CallStats],
    recent_by_provider: dict[str, CallStats],
    per_minute_by_provider: dict[tuple[str, int], int],
    recent_calls: list[RecentCall],
) -> list[ProviderHealth]:
    rows: list[ProviderHealth] = []
    for (provider,), stats in providers.items():
        if not stats.calls:
            continue
        current = recent_by_provider.get(provider, CallStats())
        peaks = [count for (name, _), count in per_minute_by_provider.items() if name == provider]
        last_call = next((c for c in recent_calls if c.provider == provider), None)
        last_error = next((c for c in recent_calls if c.provider == provider and c.error), None)
        rows.append(
            ProviderHealth(
                provider=provider,
                status=health_of(current),
                recent=current,
                peak_per_minute=max(peaks) if peaks else None,
                last_call_ms=last_call.at_ms if last_call else None,
                last_error_ms=last_error.at_ms if last_error else None,
                last_error=last_error.error if last_error else None,
            )
        )
    rows.sort(key=lambda row: (-stats_calls(providers, row.provider), row.provider))
    return rows


def stats_calls(providers: dict[tuple[str, ...], CallStats], provider: str) -> int:
    stats = providers.get((provider,))
    return stats.calls if stats else 0


def _bucket[K](groups: dict[K, CallStats], key: K) -> CallStats:
    stats = groups.get(key)
    if stats is None:
        stats = groups[key] = CallStats()
    return stats


def _rows(groups: dict[tuple[str, ...], CallStats]) -> list[GroupRow]:
    rows = [GroupRow(key=key, stats=stats) for key, stats in groups.items() if stats.calls]
    rows.sort(key=lambda row: (-row.stats.calls, row.key))
    return rows
