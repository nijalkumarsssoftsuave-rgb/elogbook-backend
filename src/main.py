"""Application entry point — the FastAPI app factory.

Wires the delivery layer: middleware, error handlers and the versioned router. Business
logic lives in the application and domain layers, not here (clean architecture).

Run locally:  uvicorn src.main:app --reload
"""

from fastapi import FastAPI

from src.api.errors.handlers import register_error_handlers
from src.api.middleware.correlation import CorrelationIdMiddleware
from src.api.v1.router import api_router
from src.core.config import settings
from src.core.logging import configure_logging, get_logger


def create_app() -> FastAPI:
    """Build and configure the application."""
    configure_logging("DEBUG" if settings.debug else "INFO")
    logger = get_logger(__name__)

    app = FastAPI(
        title="OLNG E-Logbook — Backend Service",
        version="0.1.0",
        description="System-of-record API for the OLNG E-Logbook platform.",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(CorrelationIdMiddleware)
    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    logger.info(f"{settings.app_name} started in '{settings.environment}' environment")
    return app


app = create_app()
