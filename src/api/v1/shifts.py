"""Shift-context endpoints."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from src.api.deps import Config, CurrentUser, ShiftConfigRepositoryDep, require_permission
from src.api.errors.exceptions import NotFoundError
from src.api.schemas.shift import ShiftContext, ShiftHistoryItem, ShiftHistoryResponse
from src.application.auth.resolve_permissions import resolve_query_scope, sole_area
from src.application.shifts.current_shift import resolve_current_shift
from src.application.shifts.shift_history import (
    ShiftHistoryQuery,
    get_shift_by_id,
    list_shift_history,
)
from src.core.logging import correlation_id_ctx
from src.core.response import ok

router = APIRouter(tags=["shifts"], dependencies=[Depends(require_permission("shift:read"))])


@router.get("/shifts")
async def list_shifts(
    config: Config,
    repo: ShiftConfigRepositoryDep,
    user: CurrentUser,
    date_from: Annotated[date, Query()],
    date_to: Annotated[date, Query()],
    area: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
    sort: Annotated[Literal["starts_at:asc", "starts_at:desc"], Query()] = "starts_at:desc",
) -> dict:
    """List shift windows in [date_from, date_to] (inclusive, UTC calendar dates), paginated.

    Windows are derived on every request from the versioned shift configuration
    (ES-308) — no separate shift-history table. Uses the SAME scope enforcement as
    GET /shifts/current (resolve_query_scope + sole_area) — an out-of-scope ?area= is
    403, identical semantics, not a parallel reimplementation. Large ranges are bounded
    by ``shift_history_max_range_days`` (422 if exceeded); ``page_size`` by
    ``shift_history_page_size_max`` (422 if exceeded, ``shift_history_page_size_default``
    if omitted).

    A shift that *starts* before ``date_from`` is never returned, even if it's still in
    progress and overlaps ``date_from`` for part of its duration — only shifts whose own
    start falls inside the requested range are included. If the shift configuration
    changed partway through a shift, there can also be a short window right after that
    change where no shift is returned at all for that stretch (see
    ``enumerate_shifts``'s docstring for why re-deriving it under the new configuration
    would be worse than a gap).
    """
    scope = resolve_query_scope(user.area_scope, area)
    effective_area = sole_area(scope)
    query = ShiftHistoryQuery(
        date_from=date_from,
        date_to=date_to,
        area=effective_area,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    result = await list_shift_history(repo, config, query)
    items = [
        ShiftHistoryItem(
            shift_id=s.shift_id,
            label=s.label,
            starts_at=s.starts_at.isoformat(),
            ends_at=s.ends_at.isoformat(),
            overlap_minutes=s.overlap_minutes,
            area=resolved_area,
        )
        for s, resolved_area in result.items
    ]
    payload = ShiftHistoryResponse(
        items=items,
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        total_pages=result.total_pages,
        sort=result.sort,
        scope=scope,
    )
    return ok(payload.model_dump(), correlation_id=correlation_id_ctx.get())


@router.get("/shifts/current")
async def current_shift(
    config: Config,
    repo: ShiftConfigRepositoryDep,
    user: CurrentUser,
    area: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
) -> dict:
    """Return the shift the current instant falls into (Admin-configurable window).

    Resolves from the persisted, effective-dated shift-configuration store (ES-308),
    falling back to the static bootstrap defaults if no configuration is effective yet.
    ``scope`` reports the caller's data-visibility restriction: ``None`` by default for
    the full-plant case (ES-305), or narrowed to ``?area=`` when given (ES-306) — a
    full-plant caller may narrow to any area; a scoped caller only within their own
    scope (403 otherwise). When the resolved scope pins to exactly one area, that
    area's own shift configuration is used if one exists (ES-307) — otherwise
    resolution falls back to the plant-wide configuration, and the response's ``area``
    reflects that fallback (``None``), not the lookup key.
    """
    scope = resolve_query_scope(user.area_scope, area)
    effective_area = sole_area(scope)
    shift, resolved_area = await resolve_current_shift(repo, config, now=None, area=effective_area)
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
async def get_shift(
    shift_id: str,
    config: Config,
    repo: ShiftConfigRepositoryDep,
    user: CurrentUser,
    area: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
) -> dict:
    """Return a single historical (or current) shift by its id (ES-313).

    Uses the same scope enforcement as GET /shifts and GET /shifts/current. 404 for
    an unknown or malformed id — never the old always-200 stub.
    """
    scope = resolve_query_scope(user.area_scope, area)
    effective_area = sole_area(scope)
    result = await get_shift_by_id(repo, config, shift_id, effective_area)
    if result is None:
        raise NotFoundError(f"Shift {shift_id} was not found.")
    shift, resolved_area = result
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
