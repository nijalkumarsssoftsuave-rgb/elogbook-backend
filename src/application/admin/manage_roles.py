"""Use cases: Admin-managed custom roles (BRD — custom roles with area-restricted access).

Base (system) roles are fixed platform data and cannot be created, edited or deleted
through these use cases — only the five seeded roles exist as ``is_custom=False``.
"""

from dataclasses import dataclass

from src.api.errors.exceptions import ConflictError, NotFoundError
from src.application.audit.recorder import AuditEntry, AuditRecorder
from src.application.users_roles.repository import RoleRepository
from src.domain.users_roles.entities import Role


async def list_roles(repo: RoleRepository) -> list[Role]:
    return await repo.list_all()


@dataclass(frozen=True)
class GroupRoleMapping:
    """One AD group's mapping to a role — the flat, administration-screen view.

    A role can list several AD groups, so this is one row per (group, role) pair, not
    one row per role — the shape a "which group maps to which role" screen wants,
    distinct from the full role-management view ``list_roles`` already serves.
    """

    ad_group: str
    role_id: str
    role_name: str
    is_custom: bool
    area_scope: list[str] | None


async def get_group_role_mapping(repo: RoleRepository) -> list[GroupRoleMapping]:
    """Every AD group's mapping to its role, sorted by group name (BE-US002-2)."""
    roles = await repo.list_all()
    mapping = [
        GroupRoleMapping(
            ad_group=group,
            role_id=role.id,
            role_name=role.name,
            is_custom=role.is_custom,
            area_scope=role.area_scope,
        )
        for role in roles
        for group in role.ad_groups
    ]
    return sorted(mapping, key=lambda m: m.ad_group)


async def _assert_name_and_groups_available(
    repo: RoleRepository, name: str, ad_groups: list[str], *, exclude_role_id: str | None = None
) -> None:
    for role in await repo.list_all():
        if role.id == exclude_role_id:
            continue
        if role.name == name:
            raise ConflictError(f"A role named '{name}' already exists.")
        overlap = set(ad_groups) & set(role.ad_groups)
        if overlap:
            raise ConflictError(
                f"AD group(s) already mapped to role '{role.name}': {', '.join(sorted(overlap))}"
            )


async def create_custom_role(
    repo: RoleRepository,
    *,
    name: str,
    permissions: list[str],
    ad_groups: list[str],
    area_scope: list[str] | None = None,
    audit: AuditRecorder | None = None,
    actor: str = "system",
) -> Role:
    """Create an Admin-defined custom role."""
    await _assert_name_and_groups_available(repo, name, ad_groups)
    role = Role.create_custom(name, permissions, ad_groups, area_scope)
    stored = await repo.add(role)
    if audit is not None:
        await audit.record(
            AuditEntry(
                actor=actor,
                action="role.create",
                entity_type="role",
                entity_id=stored.id,
                payload={
                    "name": stored.name,
                    "permissions": stored.permissions,
                    "ad_groups": stored.ad_groups,
                    "area_scope": stored.area_scope,
                },
            )
        )
    return stored


async def update_custom_role(
    repo: RoleRepository,
    role_id: str,
    *,
    name: str | None = None,
    permissions: list[str] | None = None,
    ad_groups: list[str] | None = None,
    area_scope: list[str] | None = ...,
    audit: AuditRecorder | None = None,
    actor: str = "system",
) -> Role:
    """Update a custom role. ``area_scope=None`` explicitly clears it to full-plant."""
    role = await repo.get(role_id)
    if role is None:
        raise NotFoundError(f"Role {role_id} was not found.")
    if not role.is_custom:
        raise ConflictError("Base roles cannot be modified.")

    new_name = name if name is not None else role.name
    new_groups = ad_groups if ad_groups is not None else role.ad_groups
    if name is not None or ad_groups is not None:
        await _assert_name_and_groups_available(repo, new_name, new_groups, exclude_role_id=role.id)

    role.name = new_name
    if permissions is not None:
        role.permissions = sorted(set(permissions))
    role.ad_groups = sorted(set(new_groups))
    if area_scope is not ...:
        role.area_scope = sorted(set(area_scope)) if area_scope else None
    role.touch()

    updated = await repo.update(role)
    if audit is not None:
        await audit.record(
            AuditEntry(
                actor=actor,
                action="role.update",
                entity_type="role",
                entity_id=updated.id,
                payload={
                    "name": updated.name,
                    "permissions": updated.permissions,
                    "ad_groups": updated.ad_groups,
                    "area_scope": updated.area_scope,
                },
            )
        )
    return updated


async def delete_custom_role(
    repo: RoleRepository,
    role_id: str,
    *,
    audit: AuditRecorder | None = None,
    actor: str = "system",
) -> None:
    role = await repo.get(role_id)
    if role is None:
        raise NotFoundError(f"Role {role_id} was not found.")
    if not role.is_custom:
        raise ConflictError("Base roles cannot be deleted.")
    await repo.delete(role_id)
    if audit is not None:
        await audit.record(
            AuditEntry(
                actor=actor,
                action="role.delete",
                entity_type="role",
                entity_id=role_id,
                payload={"name": role.name},
            )
        )
