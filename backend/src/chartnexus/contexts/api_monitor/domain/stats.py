"""Counters and the latency maths behind every row of the monitor.

Latency is stored as a histogram, not a list of timings, because the numbers
come from several processes and have to add up in Redis. Percentiles are
therefore estimates: the bucket holding the target rank is found, and the
value is interpolated linearly inside it. With the bucket edges used here the
error is a fraction of a bucket's width, which is plenty for "is Kite slow
today". The UI labels them approximate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Upper bounds (ms) of each histogram bucket but the last, which is open.
#: Must match ``infrastructure/observability/api_monitor/schema.BUCKET_BOUNDS_MS``.
BUCKET_BOUNDS_MS: tuple[int, ...] = (50, 100, 200, 300, 500, 750, 1000, 1500, 2500, 5000, 10_000)
BUCKET_COUNT = len(BUCKET_BOUNDS_MS) + 1


@dataclass(slots=True)
class CallStats:
    """Calls, errors and a latency histogram for one group of calls."""

    calls: int = 0
    total_ms: int = 0
    errors: dict[str, int] = field(default_factory=dict)
    buckets: list[int] = field(default_factory=lambda: [0] * BUCKET_COUNT)

    def add_metric(self, metric: str, value: int) -> None:
        if metric == "n":
            self.calls += value
        elif metric == "ms":
            self.total_ms += value
        elif metric.startswith("e:"):
            name = metric[2:]
            self.errors[name] = self.errors.get(name, 0) + value
        elif metric.startswith("b") and metric[1:].isdigit():
            index = int(metric[1:])
            if 0 <= index < BUCKET_COUNT:
                self.buckets[index] += value

    def merge(self, other: CallStats) -> None:
        self.calls += other.calls
        self.total_ms += other.total_ms
        for name, value in other.errors.items():
            self.errors[name] = self.errors.get(name, 0) + value
        for index, value in enumerate(other.buckets):
            self.buckets[index] += value

    @property
    def error_count(self) -> int:
        return sum(self.errors.values())

    @property
    def availability_errors(self) -> int:
        """Failures that say the provider is unwell, not that it refused us.

        A 4xx is the provider answering correctly that our request was bad (an
        expired token, a wrong symbol); counting it would mark Kite "failing"
        every morning before the user reconnects. Timeouts, connection errors,
        429s and 5xx are the provider struggling.
        """
        return sum(count for name, count in self.errors.items() if name != "http_4xx")

    @property
    def error_rate(self) -> float:
        return self.error_count / self.calls if self.calls else 0.0

    @property
    def avg_ms(self) -> float | None:
        return self.total_ms / self.calls if self.calls else None

    def percentile(self, fraction: float) -> float | None:
        return percentile_from_buckets(self.buckets, fraction)


#: Health thresholds, judged over the most recent :data:`HEALTH_WINDOW_SECONDS`.
HEALTH_WINDOW_SECONDS = 15 * 60
DOWN_ERROR_RATE = 0.5
DEGRADED_ERROR_RATE = 0.05
DEGRADED_P95_MS = 2000.0


def health_of(recent: CallStats) -> str:
    """``idle`` / ``down`` / ``degraded`` / ``healthy`` for a provider right now.

    Down means most recent calls fail; degraded means a noticeable share fail
    or the slow tail is slow. Only availability failures count (see
    :attr:`CallStats.availability_errors`); rejected requests do not. Judged on the last few minutes, not the whole
    range: a provider that broke at 10:00 and recovered at 10:05 is healthy now.
    """
    if recent.calls == 0:
        return "idle"
    failing = recent.availability_errors / recent.calls
    if failing >= DOWN_ERROR_RATE:
        return "down"
    p95 = recent.percentile(0.95)
    if failing >= DEGRADED_ERROR_RATE or (p95 is not None and p95 >= DEGRADED_P95_MS):
        return "degraded"
    return "healthy"


def percentile_from_buckets(buckets: list[int], fraction: float) -> float | None:
    """Estimate the ``fraction`` percentile (0-1) from histogram counts.

    ``None`` when there are no observations. A rank that lands in the open top
    bucket reports that bucket's lower edge: "slower than 10 s" is the honest
    answer, not an invented number above it.
    """
    total = sum(buckets)
    if total <= 0:
        return None
    fraction = min(1.0, max(0.0, fraction))
    target = fraction * total
    seen = 0
    for index, count in enumerate(buckets):
        if count <= 0:
            continue
        if seen + count >= target:
            lower = 0 if index == 0 else BUCKET_BOUNDS_MS[index - 1]
            if index >= len(BUCKET_BOUNDS_MS):
                return float(lower)
            upper = BUCKET_BOUNDS_MS[index]
            within = (target - seen) / count
            return lower + (upper - lower) * within
        seen += count
    return float(BUCKET_BOUNDS_MS[-1])
