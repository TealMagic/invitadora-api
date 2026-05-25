from fastapi import FastAPI

from app.api.routes_campaigns import router as campaigns_router
from app.api.routes_health import router as health_router
from app.api.routes_imports import router as imports_router
from app.api.routes_internal import router as internal_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_recipients import public_router as qrs_router
from app.api.routes_recipients import router as recipients_router
from app.api.routes_webhooks import router as webhooks_router
from app.core.config import get_settings
from app.core.logging import setup_logging


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(service="api", level=settings.log_level)

    app = FastAPI(title="Invitadora API", version=settings.app_version)
    app.include_router(health_router)
    app.include_router(campaigns_router)
    app.include_router(imports_router)
    app.include_router(jobs_router)
    app.include_router(recipients_router)
    app.include_router(internal_router)
    app.include_router(qrs_router)
    app.include_router(webhooks_router)
    return app


app = create_app()
