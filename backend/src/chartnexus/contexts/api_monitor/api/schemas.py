"""Response shapes for the API monitor. Labels and numbers only, never secrets.

Broker app fingerprints stay on the server: the response names a connection
only by its masked app id (``...AB12``), taken from the broker's own quota
counter.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from chartnexus.contexts.api_monitor.application.get_usage import (
    GroupRow,
    ProviderHealth,
    UsageReport,
)
from chartnexus.contexts.api_monitor.domain.stats import BUCKET_BOUNDS_MS, CallStats


def _ms(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None


class StatsModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    calls: int
    errors: int
    error_rate: float
    errors_by_class: dict[str, int]
    avg_ms: float | None
    p50_ms: float | None
    p90_ms: float | None
    p95_ms: float | None
    p99_ms: float | None

    @classmethod
    def of(cls, stats: CallStats) -> StatsModel:
        return cls(
            calls=stats.calls,
            errors=stats.error_count,
            error_rate=round(stats.error_rate, 4),
            errors_by_class=dict(sorted(stats.errors.items())),
            avg_ms=_ms(stats.avg_ms),
            p50_ms=_ms(stats.percentile(0.50)),
            p90_ms=_ms(stats.percentile(0.90)),
            p95_ms=_ms(stats.percentile(0.95)),
            p99_ms=_ms(stats.percentile(0.99)),
        )


class HistogramBucket(BaseModel):
    """Calls that took at most ``le_ms`` (``None``: slower than the last bound)."""

    le_ms: int | None
    count: int


class TotalsModel(StatsModel):
    histogram: list[HistogramBucket]

    @classmethod
    def of_totals(cls, stats: CallStats) -> TotalsModel:
        bounds: list[int | None] = [*BUCKET_BOUNDS_MS, None]
        return cls(
            **StatsModel.of(stats).model_dump(),
            histogram=[
                HistogramBucket(le_ms=bound, count=count)
                for bound, count in zip(bounds, stats.buckets, strict=True)
            ],
        )


class ProviderRow(StatsModel):
    provider: str


class EndpointRow(StatsModel):
    provider: str
    endpoint: str


class OriginRow(StatsModel):
    origin: str


class AppRow(StatsModel):
    broker: str | None
    app_label: str


class HealthModel(BaseModel):
    provider: str
    status: str
    recent_calls: int
    recent_error_rate: float
    recent_p95_ms: float | None
    peak_per_minute: int | None
    last_call_ms: int | None
    last_error_ms: int | None
    last_error: str | None

    @classmethod
    def of(cls, health: ProviderHealth) -> HealthModel:
        return cls(
            provider=health.provider,
            status=health.status,
            recent_calls=health.recent.calls,
            recent_error_rate=round(health.recent.error_rate, 4),
            recent_p95_ms=_ms(health.recent.percentile(0.95)),
            peak_per_minute=health.peak_per_minute,
            last_call_ms=health.last_call_ms,
            last_error_ms=health.last_error_ms,
            last_error=health.last_error,
        )


class SeriesPointModel(BaseModel):
    at: int
    calls: int
    errors: int
    avg_ms: float | None
    p95_ms: float | None
    by_provider: dict[str, int]


class RecentCallModel(BaseModel):
    at_ms: int
    provider: str
    endpoint: str
    origin: str
    method: str
    status: int | None
    error: str | None
    elapsed_ms: int


class QuotaModel(BaseModel):
    broker: str
    app_label: str
    used_today: int
    daily_limit: int
    window: str


class FiltersModel(BaseModel):
    provider: str | None
    origin: str | None
    endpoint: str | None


class OptionsModel(BaseModel):
    providers: list[str]
    origins: list[str]


class UsageResponse(BaseModel):
    """One report. ``scope`` says whether it is the whole platform or one user's own."""

    scope: str
    range: str
    step_seconds: int
    start: int
    end: int
    generated_at_ms: int
    filters: FiltersModel
    options: OptionsModel
    totals: TotalsModel
    previous: StatsModel | None
    calls_per_minute_now: float | None
    peak_per_minute: int | None
    health: list[HealthModel]
    providers: list[ProviderRow]
    endpoints: list[EndpointRow]
    origins: list[OriginRow]
    apps: list[AppRow]
    series: list[SeriesPointModel]
    recent: list[RecentCallModel]
    quotas: list[QuotaModel]
    percentiles_are_estimates: bool = True

    @classmethod
    def of(cls, report: UsageReport, *, scope: str) -> UsageResponse:
        def stats(row: GroupRow) -> dict[str, object]:
            return StatsModel.of(row.stats).model_dump()

        labels = {quota.app: (quota.broker, quota.app_label) for quota in report.quotas}

        return cls(
            scope=scope,
            range=report.range,
            step_seconds=report.step_seconds,
            start=report.start,
            end=report.end,
            generated_at_ms=report.end * 1000,
            filters=FiltersModel(
                provider=report.filters.provider,
                origin=report.filters.origin,
                endpoint=report.filters.endpoint,
            ),
            options=OptionsModel(providers=report.provider_options, origins=report.origin_options),
            totals=TotalsModel.of_totals(report.totals),
            previous=StatsModel.of(report.previous) if report.previous is not None else None,
            calls_per_minute_now=(
                round(report.calls_per_minute_now, 2)
                if report.calls_per_minute_now is not None
                else None
            ),
            peak_per_minute=report.peak_per_minute,
            health=[HealthModel.of(row) for row in report.health],
            providers=[ProviderRow(provider=row.key[0], **stats(row)) for row in report.providers],
            endpoints=[
                EndpointRow(provider=row.key[0], endpoint=row.key[1], **stats(row))
                for row in report.endpoints
            ],
            origins=[OriginRow(origin=row.key[0], **stats(row)) for row in report.origins],
            apps=[
                AppRow(
                    broker=labels.get(row.key[0], (None, ""))[0],
                    app_label=labels.get(row.key[0], (None, f"app {row.key[0][:6]}"))[1],
                    **stats(row),
                )
                for row in report.apps
            ],
            series=[
                SeriesPointModel(
                    at=point.at,
                    calls=point.stats.calls,
                    errors=point.stats.error_count,
                    avg_ms=_ms(point.stats.avg_ms),
                    p95_ms=_ms(point.stats.percentile(0.95)),
                    by_provider=point.by_provider,
                )
                for point in report.series
            ],
            recent=[
                RecentCallModel(
                    at_ms=call.at_ms,
                    provider=call.provider,
                    endpoint=call.endpoint,
                    origin=call.origin,
                    method=call.method,
                    status=call.status,
                    error=call.error,
                    elapsed_ms=call.elapsed_ms,
                )
                for call in report.recent
            ],
            quotas=[
                QuotaModel(
                    broker=quota.broker,
                    app_label=quota.app_label,
                    used_today=quota.used_today,
                    daily_limit=quota.daily_limit,
                    window=quota.window,
                )
                for quota in report.quotas
            ],
        )


class AdminModel(BaseModel):
    email: str
    since: str


class AuditEntryModel(BaseModel):
    at: str
    action: str
    email: str
    actor: str


class AdminsResponse(BaseModel):
    max_admins: int
    admins: list[AdminModel]
    audit: list[AuditEntryModel]
