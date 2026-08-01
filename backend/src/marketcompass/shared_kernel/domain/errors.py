"""Domain error taxonomy.

These carry no HTTP status codes on purpose — the domain does not know it is
being served over HTTP. The transport layer maps them in
:mod:`marketcompass.infrastructure.transport.http.exception_handlers`.
"""

from __future__ import annotations

from typing import Any


class MarketCompassError(Exception):
    """Base class for every error this system raises deliberately."""

    code: str = "internal_error"

    def __init__(self, message: str, /, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        return self.message


class ValidationError(MarketCompassError):
    """Input violates a domain rule (as opposed to a schema rule)."""

    code = "validation_error"


class NotFoundError(MarketCompassError):
    """The requested aggregate does not exist, or is not visible to the caller."""

    code = "not_found"

    def __init__(self, resource: str, identifier: object = None) -> None:
        super().__init__(f"{resource} not found", resource=resource, identifier=str(identifier))


class ConflictError(MarketCompassError):
    """The operation contradicts the current state of the aggregate."""

    code = "conflict"


class ConcurrencyError(ConflictError):
    """Optimistic-lock failure: the aggregate changed under us. Safe to retry."""

    code = "concurrency_conflict"


class AuthenticationError(MarketCompassError):
    """No valid principal could be established."""

    code = "unauthenticated"


class AuthorizationError(MarketCompassError):
    """The principal is known but not permitted to perform this action."""

    code = "forbidden"


class EntitlementError(AuthorizationError):
    """Blocked by the tenant's plan rather than by their role."""

    code = "entitlement_required"

    def __init__(self, feature: str, required_plan: str | None = None) -> None:
        super().__init__(
            f"feature {feature!r} is not included in the current plan",
            feature=feature,
            required_plan=required_plan,
        )


class RateLimitError(MarketCompassError):
    """The caller exceeded a quota. ``retry_after_seconds`` is advisory."""

    code = "rate_limited"

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message, retry_after_seconds=retry_after_seconds)
        self.retry_after_seconds = retry_after_seconds


class UpstreamError(MarketCompassError):
    """A dependency we do not control failed — broker, LLM, payment provider."""

    code = "upstream_unavailable"

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(message, provider=provider)
        self.provider = provider


class StaleDataError(MarketCompassError):
    """Market data exists but is too old to base an answer on."""

    code = "stale_data"

    def __init__(self, message: str, age_seconds: float | None = None) -> None:
        super().__init__(message, age_seconds=age_seconds)
