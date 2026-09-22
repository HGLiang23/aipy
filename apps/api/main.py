from fastapi import FastAPI

from aipy import __version__
from aipy.shared.config import AppSettings, get_settings

from .routes.health import ReadinessCheck
from .routes.health import router as health_router


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
    application.include_router(health_router)
    return application


app = create_app()
