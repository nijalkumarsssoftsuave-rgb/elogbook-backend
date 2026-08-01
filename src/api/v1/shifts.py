"""Shift-context endpoints."""

from fastapi import APIRouter, Depends

from src.api.deps import Config, CurrentUser, ShiftConfigRepositoryDep, require_permission
from src.api.schemas.shift import ShiftContext
from src.application.auth.resolve_permissions import resolve_query_scope
from src.application.shifts.current_shift import resolve_current_shift
from src.core.logging import correlation_id_ctx
from src.core.response import ok

router = APIRouter(tags=["shifts"], dependencies=[Depends(require_permission("shift:read"))])


@router.get("/shifts/current")
async def current_shift(config: Config, repo: ShiftConfigRepositoryDep, user: CurrentUser) -> dict:
    """Return the shift the current instant falls into (Admin-configurable window).

    Resolves from the persisted, effective-dated shift-configuration store (ES-308),
    falling back to the static bootstrap defaults if no configuration is effective yet.
    ``scope`` reports the caller's data-visibility restriction (ES-305): ``None`` for
    the default full-plant case, or the specific areas a restricted custom role is
    scoped to.
    """
    scope = resolve_query_scope(user.area_scope)
    shift, resolved_area = await resolve_current_shift(repo, config, now=None, area=None)
    payload = ShiftContext(
        shift_id=shift.shift_id,
        label=shift.label,
        starts_at=shift.starts_at.isoformat(),
        ends_at=shift.ends_at.isoformat(),
        overlap_minutes=shift.overlap_minutes,
        area=resolved_area,
        scope=scope,
    )
    return ok(payload.model_dump(), correlation_id=correlation_id_ctx.get())


@router.get("/shifts/{shift_id}")
async def get_shift(shift_id: str) -> dict:
    """Return a specific / previous shift.

    TODO: read persisted shift records from MS SQL once the persistence layer lands.
    """
    return ok({"shift_id": shift_id, "detail": "not yet implemented"})
