"""Shift-context endpoints."""

from fastapi import APIRouter, Depends

from src.api.deps import Config, require_permission
from src.api.schemas.shift import ShiftContext
from src.application.shifts.current_shift import get_current_shift
from src.core.logging import correlation_id_ctx
from src.core.response import ok

router = APIRouter(tags=["shifts"], dependencies=[Depends(require_permission("shift:read"))])


@router.get("/shifts/current")
async def current_shift(config: Config) -> dict:
    """Return the shift the current instant falls into (Admin-configurable window)."""
    shift = get_current_shift(config)
    payload = ShiftContext(
        shift_id=shift.shift_id,
        label=shift.label,
        starts_at=shift.starts_at.isoformat(),
        ends_at=shift.ends_at.isoformat(),
        overlap_minutes=shift.overlap_minutes,
    )
    return ok(payload.model_dump(), correlation_id=correlation_id_ctx.get())


@router.get("/shifts/{shift_id}")
async def get_shift(shift_id: str) -> dict:
    """Return a specific / previous shift.

    TODO: read persisted shift records from MS SQL once the persistence layer lands.
    """
    return ok({"shift_id": shift_id, "detail": "not yet implemented"})
