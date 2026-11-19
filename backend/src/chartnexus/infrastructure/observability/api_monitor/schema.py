"""The Redis layout the capture and read halves share.

* ``<prefix>:apimon:m:<epoch minute>`` - one hash per minute, kept 25 hours.
* ``<prefix>:apimon:h:<epoch hour>`` - the same counters per hour, kept 8 days.
* ``<prefix>:apimon:recent`` - the last :data:`RECENT_LIMIT` calls, newest first.

Hash fields are ``provider|endpoint|origin|app|metric``. Metrics:

* ``n`` - calls; ``ms`` - summed latency in whole milliseconds;
* ``e:<class>`` - failed calls by class (see :data:`ERROR_CLASSES`);
* ``b<i>`` - latency histogram, bucket ``i`` of :data:`BUCKET_BOUNDS_MS`
  (the last bucket is everything slower than the last bound).
"""

from __future__ import annotations

from typing import NamedTuple

MINUTE_TTL_SECONDS = 25 * 3600
HOUR_TTL_SECONDS = 8 * 86_400
RECENT_LIMIT = 500

#: Upper bounds, in ms, of every histogram bucket but the last.
BUCKET_BOUNDS_MS: tuple[int, ...] = (50, 100, 200, 300, 500, 750, 1000, 1500, 2500, 5000, 10_000)
BUCKET_COUNT = len(BUCKET_BOUNDS_MS) + 1

ERROR_CLASSES: tuple[str, ...] = (
    "timeout",
    "connect",
    "network",
    "http_4xx",
    "http_429",
    "http_5xx",
)

SEPARATOR = "|"
_FIELD_PARTS = 5


class SeriesKey(NamedTuple):
    provider: str
    endpoint: str
    origin: str
    app: str


def bucket_index(elapsed_ms: float) -> int:
    for index, bound in enumerate(BUCKET_BOUNDS_MS):
        if elapsed_ms <= bound:
            return index
    return len(BUCKET_BOUNDS_MS)


def minute_key(prefix: str, epoch_minute: int) -> str:
    return f"{prefix}:apimon:m:{epoch_minute}"


def hour_key(prefix: str, epoch_hour: int) -> str:
    return f"{prefix}:apimon:h:{epoch_hour}"


def recent_key(prefix: str) -> str:
    return f"{prefix}:apimon:recent"


def encode_field(series: SeriesKey, metric: str) -> str:
    return SEPARATOR.join((*series, metric))


def parse_field(raw: str) -> tuple[SeriesKey, str] | None:
    parts = raw.split(SEPARATOR)
    if len(parts) != _FIELD_PARTS:
        return None
    provider, endpoint, origin, app, metric = parts
    return SeriesKey(provider, endpoint, origin, app), metric
