"""Shift-context endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import Config, PendingActionUoW, require_permission
from src.api.errors.exceptions import ValidationError
from src.api.schemas.pending_action import ActionResponse
from src.api.schemas.shift import ShiftActionsReport, ShiftContext
from src.application.auth.resolve_permissions import is_in_area_scope
from src.application.shifts.current_shift import get_current_shift
from src.application.shifts.shift_actions_report import get_actions_for_shift
from src.core.logging import correlation_id_ctx
from src.core.response import ok
from src.domain.shifts.entities import Shift
from src.infrastructure.auth.token_validator import Principal

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


@router.get("/shifts/{shift_id}/actions")
async def shift_actions_report(
    shift_id: str,
    config: Config,
    uow: PendingActionUoW,
    user: Annotated[Principal, Depends(require_permission("action:read"))],
) -> dict:
    """Confirmed actions captured during one shift's window (ES-344).

    Explicitly re-checks ``action:read`` on top of the router's ``shift:read`` — this
    exposes pending-action data, not just shift metadata, so it should require the same
    permission the pending-actions endpoints themselves do. Restricted to the caller's
    area scope, same as ``GET /pending-actions``.
    """
    try:
        shift = Shift.from_id(
            shift_id,
            start_hour=config.shift_start_hour,
            hours=config.shift_hours,
            overlap_minutes=config.shift_overlap_minutes,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    actions = await get_actions_for_shift(uow.actions, shift)
    visible = [a for a in actions if is_in_area_scope(a.area, user.area_scope)]
    payload = ShiftActionsReport(
        shift_id=shift.shift_id,
        label=shift.label,
        starts_at=shift.starts_at.isoformat(),
        ends_at=shift.ends_at.isoformat(),
        actions=[ActionResponse.of(a) for a in visible],
    )
    return ok(payload.model_dump(), correlation_id=correlation_id_ctx.get())
