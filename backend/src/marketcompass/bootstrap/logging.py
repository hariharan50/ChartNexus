"""Logging composition root."""

from __future__ import annotations

from marketcompass.bootstrap.settings import Settings
from marketcompass.infrastructure.observability.structured_logging import configure_structlog


def configure_logging(settings: Settings) -> None:
    """Configure logging for a process. Call once, before anything else logs."""
    configure_structlog(
        level=settings.observability.log_level,
        output=settings.observability.log_format,
        service_name=settings.observability.service_name,
    )
