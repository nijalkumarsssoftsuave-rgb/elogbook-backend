"""Aggregate the v1 routers into a single API router."""

from fastapi import APIRouter

from src.api.v1 import admin, dev_auth, health, me, pending_actions, shifts

api_router = APIRouter()

# --- implemented ---
api_router.include_router(health.router)
api_router.include_router(dev_auth.router)
api_router.include_router(me.router)
api_router.include_router(shifts.router)
api_router.include_router(pending_actions.router)
api_router.include_router(admin.router)

# --- to be added as each feature lands (routers scaffolded, endpoints TODO) ---
# from src.api.v1 import summaries, notifications, superuser
# api_router.include_router(summaries.router)
# api_router.include_router(notifications.router)
# api_router.include_router(superuser.router)
