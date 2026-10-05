"""Health endpoints.

Three distinct probes, because Kubernetes treats them differently:

``/health/live``   process is up. Never touches a dependency — a failing
                   database must not get the pod killed and restarted.
``/health/ready``  process can serve traffic. Checks Postgres and Redis.
``/health/startup`` slower budget for the initial boot.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Response, status

CheckFn = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    name: str
    check: CheckFn
    timeout_seconds: float = 2.0


def build_health_router(
    *,
    version: str,
    checks: tuple[DependencyCheck, ...] = (),
) -> APIRouter:
    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("/live", summary="Liveness probe")
    async def live() -> dict[str, str]:
        return {"status": "ok", "version": version}

    @router.get("/ready", summary="Readiness probe")
    async def ready(response: Response) -> dict[str, object]:
        results = await _run_checks(checks)
        healthy = all(state == "ok" for state in results.values())
        if not healthy:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "ok" if healthy else "degraded",
            "version": version,
            "dependencies": results,
        }

    @router.get("/startup", summary="Startup probe")
    async def startup(response: Response) -> dict[str, object]:
        return await ready(response)

    return router


async def _run_checks(checks: tuple[DependencyCheck, ...]) -> dict[str, str]:
    if not checks:
        return {}

    async def run(dependency: DependencyCheck) -> tuple[str, str]:
        try:
            async with asyncio.timeout(dependency.timeout_seconds):
                await dependency.check()
        except TimeoutError:
            return dependency.name, "timeout"
        except Exception as exc:
            return dependency.name, f"error: {type(exc).__name__}"
        return dependency.name, "ok"

    outcomes = await asyncio.gather(*(run(dependency) for dependency in checks))
    return dict(outcomes)


HealthStatus = Literal["ok", "degraded"]
