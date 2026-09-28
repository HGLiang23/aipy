from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aipy import __version__
from aipy.shared.config import AppSettings, get_settings

from .dependencies import get_jwt_service, get_session_factory
from .middleware import RequestIdMiddleware
from .routes.auth import router as auth_router
from .routes.health import ReadinessCheck, default_readiness_checks
from .routes.health import router as health_router
from .routes.human_tasks import router as human_tasks_router
from .routes.materials import router as materials_router
from .routes.organization import router as organization_router
from .routes.workflow_runs import router as workflow_runs_router
from .schemas import ProblemDetails


def _problem(status_code: int, detail: str | None, code: str = "http_error") -> JSONResponse:
    pd = ProblemDetails(
        status=status_code,
        title=HTTPStatus(status_code).phrase,
        detail=detail,
        code=code,
    )
    return JSONResponse(status_code=status_code, content=pd.model_dump())


def create_app(
    settings: AppSettings | None = None,
    *,
    readiness_checks: dict[str, ReadinessCheck] | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    application = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        debug=resolved_settings.debug,
    )
    application.state.settings = resolved_settings
    # Warm the engine/session factory so connection errors surface at startup.
    application.state.session_factory = get_session_factory()
    # Readiness must prove the real dependencies are reachable; only an explicit
    # mapping from the caller (tests) replaces the default database/Redis probes.
    application.state.readiness_checks = (
        readiness_checks
        if readiness_checks is not None
        else default_readiness_checks(
            application.state.session_factory, resolved_settings.redis.url
        )
    )
    # Build the token service eagerly: a missing signing key must fail at boot,
    # not halfway through the first login.
    application.state.jwt_service = get_jwt_service()

    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.add_exception_handler(RequestValidationError, _validation_handler)
    application.add_exception_handler(HTTPException, _http_exception_handler)

    application.include_router(health_router)
    application.include_router(auth_router, prefix="/api/v1")
    application.include_router(workflow_runs_router, prefix="/api/v1")
    application.include_router(human_tasks_router, prefix="/api/v1")
    application.include_router(materials_router, prefix="/api/v1")
    application.include_router(organization_router, prefix="/api/v1")
    return application


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    if isinstance(exc.detail, dict):
        return _problem(
            exc.status_code,
            exc.detail.get("detail"),
            exc.detail.get("code", "http_error"),
        )
    return _problem(exc.status_code, exc.detail if isinstance(exc.detail, str) else None)


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    return _problem(422, "request validation failed")


app = create_app()
