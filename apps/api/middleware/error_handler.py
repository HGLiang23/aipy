"""Global error handlers mapping domain/infrastructure exceptions to HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError

from aipy.shared.security.errors import (
    AuthenticationError,
    AuthorizationDeniedError,
    SecurityError,
)


def _problem_json(
    status_code: int,
    code: str,
    detail: str,
    request: Request | None = None,
    **extra,
) -> JSONResponse:
    body: dict = {
        "type": f"https://api.aipy.dev/problems/{code.lower()}",
        "title": detail,
        "status": status_code,
        "code": code,
        "detail": detail,
    }
    if extra:
        body.update(extra)
    if request is not None:
        body["instance"] = str(request.url.path)
        body["request_id"] = getattr(request.state, "request_id", None)
    return JSONResponse(status_code=status_code, content=body)


def register_error_handlers(app: FastAPI) -> None:

    @app.exception_handler(SecurityError)
    async def _security_error(request: Request, exc: SecurityError) -> JSONResponse:
        status = 401 if isinstance(exc, AuthenticationError) else 403
        return _problem_json(status, exc.code, exc.detail, request, metadata=exc.metadata)

    @app.exception_handler(IntegrityError)
    async def _integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        return _problem_json(409, "INTEGRITY_VIOLATION", "Resource conflict", request)

    @app.exception_handler(OperationalError)
    async def _operational_error(request: Request, exc: OperationalError) -> JSONResponse:
        return _problem_json(503, "DATABASE_UNAVAILABLE", "Database temporarily unavailable", request)
