"""Health & readiness endpoints."""

from fastapi import APIRouter

from src.core.config import settings
from src.core.response import ok

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — the service is up."""
    return ok({"status": "ok", "service": settings.app_name, "environment": settings.environment})


@router.get("/ready")
async def ready() -> dict:
    """Readiness probe.

    TODO: check MS SQL, Valkey and ai-service reachability once those adapters land.
    """
    return ok({"status": "ready", "checks": {"db": "skipped", "cache": "skipped", "ai": "skipped"}})
