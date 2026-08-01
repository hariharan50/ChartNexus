"""structlog configuration.

Logs are JSON in every environment except local development, where a coloured
console renderer is easier to read. Request-scoped fields (request id, tenant,
user) are merged in from the contextvars set by
:mod:`marketcompass.infrastructure.observability.request_context`.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Literal

import structlog
from structlog.types import Processor

_STDLIB_NOISE = {
    "uvicorn.access": logging.WARNING,
    "sqlalchemy.engine": logging.WARNING,
    "asyncio": logging.WARNING,
    "celery.app.trace": logging.WARNING,
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
}


def configure_structlog(
    *,
    level: str = "INFO",
    output: Literal["json", "console"] = "json",
    service_name: str = "marketcompass",
) -> None:
    """Configure structlog and route the stdlib logging tree through it."""
    numeric_level = logging.getLevelNamesMapping()[level]

    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        _add_service_name(service_name),
    ]

    renderer: Processor
    if output == "json":
        shared.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    for name, noise_level in _STDLIB_NOISE.items():
        logging.getLogger(name).setLevel(max(numeric_level, noise_level))


def _add_service_name(service_name: str) -> Processor:
    def processor(
        _logger: Any, _method: str, event_dict: structlog.types.EventDict
    ) -> structlog.types.EventDict:
        event_dict.setdefault("service", service_name)
        return event_dict

    return processor


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger. Prefer module-level ``log = get_logger(__name__)``."""
    return structlog.stdlib.get_logger(name)
