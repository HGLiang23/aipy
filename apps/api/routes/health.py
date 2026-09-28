"""Liveness and readiness endpoints.

Liveness only proves the process is up. Readiness must prove the instance can
actually serve traffic, so by default it probes the two hard dependencies - the
database and Redis. A deployment that wires ``/health/ready`` into a
Kubernetes ``readinessProbe`` without those probes would keep routing traffic to
an instance that cannot reach PostgreSQL.
"""

import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Literal

import anyio
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import text

from aipy.shared.db import SessionFactory

type ReadinessCheck = Callable[[], bool | Awaitable[bool]]

DATABASE_CHECK = "database"
REDIS_CHECK = "redis"

#: Hard ceiling for a single dependency probe, so a hung dependency cannot hold
#: the readiness request open indefinitely.
PROBE_TIMEOUT_SECONDS = 2.0

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["alive", "ready", "not_ready"]
    checks: dict[str, bool] | None = None


def _probe_database(factory: SessionFactory) -> bool:
    """Open a pooled connection and run the cheapest possible round trip."""

    with factory() as session:
        session.execute(text("SELECT 1"))
    return True


def _probe_redis(url: str) -> bool:
    client = Redis.from_url(
        url,
        socket_connect_timeout=PROBE_TIMEOUT_SECONDS,
        socket_timeout=PROBE_TIMEOUT_SECONDS,
    )
    try:
        return bool(client.ping())
    finally:
        client.close()


def _offloaded(probe: Callable[[], bool]) -> ReadinessCheck:
    """Run a blocking driver call in a worker thread instead of the event loop."""

    async def check() -> bool:
        return bool(await anyio.to_thread.run_sync(probe))

    return check


def default_readiness_checks(
    session_factory: SessionFactory, redis_url: str
) -> dict[str, ReadinessCheck]:
    """Dependency probes used unless the caller supplies its own mapping."""

    return {
        DATABASE_CHECK: _offloaded(functools.partial(_probe_database, session_factory)),
        REDIS_CHECK: _offloaded(functools.partial(_probe_redis, redis_url)),
    }


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    return HealthResponse(status="alive")


@router.get("/ready", response_model=HealthResponse)
async def readiness(request: Request) -> HealthResponse | JSONResponse:
    checks: dict[str, bool] = {}
    registered_checks: dict[str, ReadinessCheck] = request.app.state.readiness_checks

    for name, check in registered_checks.items():
        try:
            result = check()
            if inspect.isawaitable(result):
                result = await result
            checks[name] = result is True
        except Exception:
            checks[name] = False

    response = HealthResponse(
        status="ready" if all(checks.values()) else "not_ready",
        checks=checks,
    )
    if response.status == "not_ready":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(),
        )
    return response
