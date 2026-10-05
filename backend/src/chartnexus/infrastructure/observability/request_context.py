"""Request-scoped ambient context.

Anything bound here is automatically attached to every log line emitted while
handling the request, and is available to repositories that need the acting
tenant without threading it through every call signature.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

import structlog

_request_id: ContextVar[str | None] = ContextVar("cn_request_id", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("cn_tenant_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("cn_user_id", default=None)


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str | None
    tenant_id: str | None
    user_id: str | None


def current_context() -> RequestContext:
    return RequestContext(
        request_id=_request_id.get(),
        tenant_id=_tenant_id.get(),
        user_id=_user_id.get(),
    )


def current_request_id() -> str | None:
    return _request_id.get()


def current_tenant_id() -> str | None:
    return _tenant_id.get()


def require_tenant_id() -> str:
    """Return the acting tenant, or fail loudly.

    Called by tenant-scoped repositories: a missing tenant is a bug that must
    never silently widen a query to every tenant's rows.
    """
    tenant_id = _tenant_id.get()
    if tenant_id is None:
        msg = "no tenant bound to the current context"
        raise LookupError(msg)
    return tenant_id


@contextmanager
def bind_request_context(
    *,
    request_id: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> Iterator[None]:
    """Bind context for the duration of a request, task, or message."""
    tokens = (
        _request_id.set(request_id),
        _tenant_id.set(tenant_id),
        _user_id.set(user_id),
    )
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    try:
        yield
    finally:
        structlog.contextvars.unbind_contextvars("request_id", "tenant_id", "user_id")
        _request_id.reset(tokens[0])
        _tenant_id.reset(tokens[1])
        _user_id.reset(tokens[2])


def bind_principal(*, tenant_id: str | None, user_id: str | None) -> None:
    """Attach the authenticated principal once authentication has resolved it."""
    _tenant_id.set(tenant_id)
    _user_id.set(user_id)
    structlog.contextvars.bind_contextvars(tenant_id=tenant_id, user_id=user_id)
