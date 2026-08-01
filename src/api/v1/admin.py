"""Admin: custom role management (BRD — custom roles with area-restricted access).

Base (system) roles ship as fixed platform data and are read-only here; only custom
roles an Administrator creates can be edited or deleted. Every mutation is audited in
the same hash-chained trail as pending-actions.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import AuditReaderDep, RoleRepositoryDep, RoleUoW, UserUoW, require_permission
from src.api.schemas.audit import AuditEntryResponse
from src.api.schemas.role import (
    CreateRoleRequest,
    RoleMappingEntryResponse,
    RoleResponse,
    UpdateRoleRequest,
)
from src.api.schemas.user import AdminUserResponse, CreateUserRequest, UpdateUserRequest
from src.application.admin.manage_roles import (
    create_custom_role,
    delete_custom_role,
    get_group_role_mapping,
    list_roles,
    update_custom_role,
)
from src.application.admin.manage_users import (
    create_user,
    delete_user,
    get_user,
    list_users,
    update_user,
)
from src.core.logging import correlation_id_ctx
from src.core.response import ok
from src.infrastructure.auth.token_validator import Principal

router = APIRouter(prefix="/admin", tags=["admin"])


def _cid() -> str:
    return correlation_id_ctx.get()


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
    user_uow: UserUoW,
    user: Annotated[Principal, Depends(require_permission("role:manage"))],
) -> dict:
    """Delete a custom role.

    Base roles cannot be deleted (409). Fails (409) if users are assigned.
    """
    await delete_custom_role(
        uow.roles, role_id, user_repo=user_uow.users, audit=uow.audit, actor=user.username
    )
    return ok({"deleted": role_id}, correlation_id=_cid())


# ---------------------------------------------------------------------------
# User CRUD (ES-358)
# ---------------------------------------------------------------------------


@router.get("/users/{user_id}/history", dependencies=[Depends(require_permission("user:read"))])
async def user_history_endpoint(user_id: str, reader: AuditReaderDep) -> dict:
    """The admin user record's change history, most recent first.

    Not gated on the user currently existing — a deleted user's history is still
    auditable governance data and stays readable. An unknown ``user_id`` simply yields
    an empty list.
    """
    entries = await reader.list_for_entity("user", user_id)
    return ok([AuditEntryResponse.of(e).model_dump() for e in entries], correlation_id=_cid())


@router.get("/users", dependencies=[Depends(require_permission("user:read"))])
async def list_users_endpoint(uow: UserUoW) -> dict:
    """List all admin-provisioned users."""
    result = await list_users(uow.users)
    return ok([AdminUserResponse.of(u).model_dump() for u in result], correlation_id=_cid())


@router.get("/users/{user_id}", dependencies=[Depends(require_permission("user:read"))])
async def get_user_endpoint(user_id: str, uow: UserUoW) -> dict:
    """Get a single admin-provisioned user by ID."""
    result = await get_user(uow.users, user_id)
    return ok(AdminUserResponse.of(result).model_dump(), correlation_id=_cid())


@router.post("/users")
async def create_user_endpoint(
    body: CreateUserRequest,
    uow: UserUoW,
    role_repo: RoleRepositoryDep,
    actor: Annotated[Principal, Depends(require_permission("user:manage"))],
) -> dict:
    """Provision a new user, optionally with a manual role override."""
    result = await create_user(
        uow.users,
        username=body.username,
        display_name=body.display_name,
        email=body.email,
        role_id=body.role_id,
        role_repo=role_repo,
        audit=uow.audit,
        actor=actor.username,
    )
    return ok(AdminUserResponse.of(result).model_dump(), correlation_id=_cid())


@router.patch("/users/{user_id}")
async def update_user_endpoint(
    user_id: str,
    body: UpdateUserRequest,
    uow: UserUoW,
    role_repo: RoleRepositoryDep,
    actor: Annotated[Principal, Depends(require_permission("user:manage"))],
) -> dict:
    """Update a user. Pass ``clear_role: true`` to remove the manual role override."""
    role_id_kwarg: dict = {}
    if body.clear_role:
        role_id_kwarg["role_id"] = None
    elif body.role_id is not None:
        role_id_kwarg["role_id"] = body.role_id

    result = await update_user(
        uow.users,
        user_id,
        display_name=body.display_name,
        email=body.email,
        is_active=body.is_active,
        role_repo=role_repo,
        audit=uow.audit,
        actor=actor.username,
        **role_id_kwarg,
    )
    return ok(AdminUserResponse.of(result).model_dump(), correlation_id=_cid())


@router.delete("/users/{user_id}")
async def delete_user_endpoint(
    user_id: str,
    uow: UserUoW,
    actor: Annotated[Principal, Depends(require_permission("user:manage"))],
) -> dict:
    """Delete a user record."""
    await delete_user(uow.users, user_id, audit=uow.audit, actor=actor.username)
    return ok({"deleted": user_id}, correlation_id=_cid())
