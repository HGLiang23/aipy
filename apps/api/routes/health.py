import inspect
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

type ReadinessCheck = Callable[[], bool | Awaitable[bool]]

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["alive", "ready", "not_ready"]
    checks: dict[str, bool] | None = None


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
