"""Admin: custom role management (BRD — custom roles with area-restricted access).

Base (system) roles ship as fixed platform data and are read-only here; only custom
roles an Administrator creates can be edited or deleted. Every mutation is audited in
the same hash-chained trail as pending-actions.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import AuditReaderDep, RoleUoW, require_permission
from src.api.schemas.audit import AuditEntryResponse
from src.api.schemas.role import (
    CreateRoleRequest,
    RoleMappingEntryResponse,
    RoleResponse,
    UpdateRoleRequest,
)
from src.application.admin.manage_roles import (
    create_custom_role,
    delete_custom_role,
    get_group_role_mapping,
    list_known_areas,
    list_roles,
    update_custom_role,
)
from src.core.logging import correlation_id_ctx
from src.core.response import ok
from src.infrastructure.auth.token_validator import Principal

router = APIRouter(prefix="/admin", tags=["admin"])


def _cid() -> str:
    return correlation_id_ctx.get()


@router.get("/areas", dependencies=[Depends(require_permission("role:read"))])
async def list_areas_endpoint(uow: RoleUoW) -> dict:
    """List every distinct area name currently in use across all roles, sorted alphabetically.

    Used by the UI to populate the area-scope picker when creating or editing a scoped
    role. Returns an empty list when no scoped roles exist yet — the list grows
    automatically as administrators create area-restricted roles.
    """
    areas = await list_known_areas(uow.roles)
    return ok(areas, correlation_id=_cid())


@router.get("/roles", dependencies=[Depends(require_permission("role:read"))])
async def list_roles_endpoint(uow: RoleUoW) -> dict:
    """List every role — base (system) and custom."""
    roles = await list_roles(uow.roles)
    return ok([RoleResponse.of(r).model_dump() for r in roles], correlation_id=_cid())


@router.get("/roles/mapping", dependencies=[Depends(require_permission("role:read"))])
async def role_mapping_endpoint(uow: RoleUoW) -> dict:
    """The AD-group-to-role mapping, flat and lean, for the administration screen
    (BE-US002-2) — one row per (group, role), not the full role objects ``/roles``
    returns.
    """
    mapping = await get_group_role_mapping(uow.roles)
    return ok([RoleMappingEntryResponse.of(m).model_dump() for m in mapping], correlation_id=_cid())


@router.get("/roles/{role_id}/history", dependencies=[Depends(require_permission("role:read"))])
async def role_history_endpoint(role_id: str, reader: AuditReaderDep) -> dict:
    """The AD-group-to-role mapping's change history, most recent first (BE-US002-1).

    Not gated on the role currently existing — a deleted role's history is still
    governed configuration and stays readable. An unknown ``role_id`` simply yields an
    empty list, the same as a role that never had any changes.
    """
    entries = await reader.list_for_entity("role", role_id)
    return ok([AuditEntryResponse.of(e).model_dump() for e in entries], correlation_id=_cid())


@router.post("/roles")
async def create_role(
    body: CreateRoleRequest,
    uow: RoleUoW,
    user: Annotated[Principal, Depends(require_permission("role:manage"))],
) -> dict:
    """Create a custom role with its own permissions and (optional) area restriction."""
    role = await create_custom_role(
        uow.roles,
        name=body.name,
        permissions=body.permissions,
        ad_groups=body.ad_groups,
        area_scope=body.area_scope,
        audit=uow.audit,
        actor=user.username,
    )
    return ok(RoleResponse.of(role).model_dump(), correlation_id=_cid())


@router.patch("/roles/{role_id}")
async def update_role(
    role_id: str,
    body: UpdateRoleRequest,
    uow: RoleUoW,
    user: Annotated[Principal, Depends(require_permission("role:manage"))],
) -> dict:
    """Update a custom role. Base roles cannot be modified (409)."""
    area_scope_kwargs = {}
    if body.clear_area_scope:
        area_scope_kwargs["area_scope"] = None
    elif body.area_scope is not None:
        area_scope_kwargs["area_scope"] = body.area_scope

    role = await update_custom_role(
        uow.roles,
        role_id,
        name=body.name,
        permissions=body.permissions,
        ad_groups=body.ad_groups,
        audit=uow.audit,
        actor=user.username,
        **area_scope_kwargs,
    )
    return ok(RoleResponse.of(role).model_dump(), correlation_id=_cid())


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: str,
    uow: RoleUoW,
    user: Annotated[Principal, Depends(require_permission("role:manage"))],
) -> dict:
    """Delete a custom role. Base roles cannot be deleted (409)."""
    await delete_custom_role(uow.roles, role_id, audit=uow.audit, actor=user.username)
    return ok({"deleted": role_id}, correlation_id=_cid())
