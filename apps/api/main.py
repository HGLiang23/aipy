from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from http import HTTPStatus

from aipy import __version__
from aipy.shared.config import AppSettings, get_settings

from .dependencies import get_session_factory
from .routes.health import ReadinessCheck
from .routes.health import router as health_router
from .routes.auth import router as auth_router
from .routes.workflow_runs import router as workflow_runs_router
from .routes.human_tasks import router as human_tasks_router
from .routes.materials import router as materials_router
from .routes.members import router as members_router
from .routes.roles import router as roles_router
from .routes.workflow_templates import router as workflow_templates_router
from .routes.audit_logs import router as audit_logs_router
from .routes.model_credentials import router as model_credentials_router
from .routes.model_routing import router as model_routing_router
from .routes.quotas import router as quotas_router
from .schemas import ProblemDetails


def _problem(status_code: int, detail: str | None) -> JSONResponse:
    pd = ProblemDetails(
        status=status_code,
        title=HTTPStatus(status_code).phrase,
        detail=detail,
        code="http_error",
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
    application.state.readiness_checks = readiness_checks or {}
    # Warm the engine/session factory so connection errors surface at startup.
    application.state.session_factory = get_session_factory()

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
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
    application.include_router(members_router, prefix="/api/v1")
    application.include_router(roles_router, prefix="/api/v1")
    application.include_router(workflow_templates_router, prefix="/api/v1")
    application.include_router(audit_logs_router, prefix="/api/v1")
    application.include_router(model_credentials_router, prefix="/api/v1")
    application.include_router(model_routing_router, prefix="/api/v1")
    application.include_router(quotas_router, prefix="/api/v1")
    return application


async def _http_exception_handler(request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else None
    return _problem(exc.status_code, detail)


async def _validation_handler(request, exc: RequestValidationError) -> JSONResponse:
    return _problem(422, "request validation failed")


app = create_app()
