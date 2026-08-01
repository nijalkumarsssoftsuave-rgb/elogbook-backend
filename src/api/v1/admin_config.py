"""Admin: shift configuration (US-008 — EP-04, ES-308/309/310/311).

A new router, kept separate from ``admin.py`` (role management, a different developer's
territory) though both live under ``/admin``; they coexist fine under different path
prefixes. Shift configuration is append-only and effective-dated — see
``application/admin/manage_config.py``. Every mutation is audited in the same
hash-chained trail as pending-actions and role changes (ES-311).
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.deps import (
    AuditReaderDep,
    ShiftConfigRepositoryDep,
    ShiftConfigUoW,
    require_permission,
)
from src.api.schemas.audit import AuditEntryResponse
from src.api.schemas.shift_config import CreateShiftConfigRequest, ShiftConfigResponse
from src.application.admin.manage_config import (
    create_shift_configuration,
    list_shift_configurations,
)
from src.core.logging import correlation_id_ctx
from src.core.response import ok
from src.domain.shifts.entities import ShiftConfiguration
from src.infrastructure.auth.token_validator import Principal

router = APIRouter(prefix="/admin/config", tags=["admin", "shift-config"])


def _cid() -> str:
    return correlation_id_ctx.get()


@router.get("/shift", dependencies=[Depends(require_permission("config:read"))])
async def get_effective_shift_config(
    repo: ShiftConfigRepositoryDep,
    area: Annotated[str | None, Query()] = None,
) -> dict:
    """The shift configuration currently in effect, optionally narrowed to ``area``."""
    configs = await list_shift_configurations(repo)
    cfg = ShiftConfiguration.effective_for(configs, datetime.now(UTC), area)
    data = ShiftConfigResponse.of(cfg).model_dump() if cfg is not None else None
    return ok(data, correlation_id=_cid())


@router.get("/shift/versions", dependencies=[Depends(require_permission("config:read"))])
async def list_shift_config_versions(repo: ShiftConfigRepositoryDep) -> dict:
    """Every persisted shift-configuration version, newest first."""
    configs = await list_shift_configurations(repo)
    newest_first = sorted(configs, key=lambda c: (c.effective_from, c.version), reverse=True)
    return ok([ShiftConfigResponse.of(c).model_dump() for c in newest_first], correlation_id=_cid())


@router.get("/shift/history", dependencies=[Depends(require_permission("config:read"))])
async def shift_config_history(
    reader: AuditReaderDep,
    area: Annotated[str | None, Query()] = None,
) -> dict:
    """Change history for one area's (or the plant-wide) shift configuration.

    Reads back the ``shift_config.create`` audit trail keyed by ``area`` (``"__plant__"``
    for the plant-wide row). Returns ``[]`` cleanly under the ``memory`` backend, same as
    every other admin history view (``NullAuditReader``).
    """
    entity_id = area if area is not None else "__plant__"
    entries = await reader.list_for_entity("shift_config", entity_id)
    return ok([AuditEntryResponse.of(e).model_dump() for e in entries], correlation_id=_cid())


@router.post("/shift")
async def create_shift_config(
    body: CreateShiftConfigRequest,
    uow: ShiftConfigUoW,
    user: Annotated[Principal, Depends(require_permission("config:manage"))],
) -> dict:
    """Append a new shift-configuration version.

    409 on a stale ``expected_version`` or a retro-dated ``effective_from``; 422 on
    out-of-range ``start_hour``/``hours``/``overlap_minutes``.
    """
    config = await create_shift_configuration(
        uow,
        area=body.area,
        start_hour=body.start_hour,
        hours=body.hours,
        overlap_minutes=body.overlap_minutes,
        effective_from=body.effective_from,
        expected_version=body.expected_version,
        actor=user.username,
    )
    return ok(ShiftConfigResponse.of(config).model_dump(), correlation_id=_cid())
