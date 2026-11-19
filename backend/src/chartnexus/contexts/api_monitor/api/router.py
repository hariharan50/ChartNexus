"""API monitor routes.

* ``GET /admin/api-monitor`` - every outbound call on the platform. Admins only.
* ``GET /admin/admins`` - who the admins are and recent role changes. Admins only.
* ``GET /api-monitor/mine`` - the caller's own broker usage. Any signed-in user.

The admin check reads the role from the database on every request rather than
trusting the access token, so revoking admin takes effect immediately instead
of when the token expires. A refusal is a plain 403 that says nothing about
what the page would have shown.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from chartnexus.contexts.api_monitor.api.dependencies import Services
from chartnexus.contexts.api_monitor.api.schemas import (
    AdminModel,
    AdminsResponse,
    AuditEntryModel,
    UsageResponse,
)
from chartnexus.contexts.api_monitor.application.get_usage import UsageFilters
from chartnexus.infrastructure.observability.structured_logging import get_logger
from chartnexus.infrastructure.transport.http.dependencies import CurrentPrincipal, Principal
from chartnexus.shared_kernel.domain.errors import AuthorizationError

log = get_logger(__name__)

router = APIRouter(tags=["api-monitor"])

RangeParam = Literal["1h", "6h", "24h", "7d"]

_AUDIT_ROWS = 50
_MAX_FILTER_LENGTH = 120

ProviderParam = Query(default=None, max_length=_MAX_FILTER_LENGTH)
OriginParam = Query(default=None, max_length=_MAX_FILTER_LENGTH)
EndpointParam = Query(default=None, max_length=_MAX_FILTER_LENGTH)


def _filters(provider: object, origin: object, endpoint: object) -> UsageFilters:
    """Narrow a report. Values are matched exactly against stored labels."""

    def value(raw: object) -> str | None:
        return raw.strip() or None if isinstance(raw, str) else None

    return UsageFilters(provider=value(provider), origin=value(origin), endpoint=value(endpoint))


async def _require_admin(principal: Principal, services: Services) -> None:
    if not await services.gate.is_admin(principal.user_id):
        log.warning("admin_access_denied", user_id=str(principal.user_id))
        raise AuthorizationError("You do not have permission to view this page.")


@router.get(
    "/admin/api-monitor",
    response_model=UsageResponse,
    summary="Every outbound API call on the platform (admin only)",
)
async def admin_overview(
    principal: CurrentPrincipal,
    services: Services,
    *,
    range_: RangeParam = Query(default="1h", alias="range"),
    provider: str | None = ProviderParam,
    origin: str | None = OriginParam,
    endpoint: str | None = EndpointParam,
) -> UsageResponse:
    await _require_admin(principal, services)
    log.info("admin_api_monitor_viewed", user_id=str(principal.user_id), range=range_)
    report = await services.usage.report(
        range_, apps=None, filters=_filters(provider, origin, endpoint)
    )
    return UsageResponse.of(report, scope="platform")


@router.get(
    "/admin/admins",
    response_model=AdminsResponse,
    summary="Platform admins and recent admin changes (admin only)",
)
async def admin_roster(principal: CurrentPrincipal, services: Services) -> AdminsResponse:
    await _require_admin(principal, services)
    admins = await services.roster.admins()
    audit = await services.roster.audit(_AUDIT_ROWS)
    return AdminsResponse(
        max_admins=services.max_admins,
        admins=[AdminModel(email=admin.email, since=admin.since) for admin in admins],
        audit=[
            AuditEntryModel(
                at=entry.get("at", ""),
                action=entry.get("action", ""),
                email=entry.get("email", ""),
                actor=entry.get("actor", ""),
            )
            for entry in audit
        ],
    )


@router.get(
    "/api-monitor/mine",
    response_model=UsageResponse,
    summary="The caller's own broker usage",
    description=(
        "Only calls made with the caller's own broker app (Kite or FYERS) are counted. "
        "Market-wide jobs that happen to use this connection are included, because "
        "they spend this connection's quota."
    ),
)
async def my_usage(
    principal: CurrentPrincipal,
    services: Services,
    *,
    range_: RangeParam = Query(default="24h", alias="range"),
    provider: str | None = ProviderParam,
    origin: str | None = OriginParam,
    endpoint: str | None = EndpointParam,
) -> UsageResponse:
    apps = await services.gate.own_apps(principal.tenant_id)
    report = await services.usage.report(
        range_, apps=apps, filters=_filters(provider, origin, endpoint)
    )
    return UsageResponse.of(report, scope="mine")
