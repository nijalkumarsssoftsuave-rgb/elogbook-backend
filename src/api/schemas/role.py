"""Role request/response schemas (admin role management)."""

import re

from pydantic import BaseModel, Field, field_validator

from src.application.admin.manage_roles import GroupRoleMapping
from src.domain.users_roles.entities import Role

_ROLE_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
_PERMISSION_RE = re.compile(r"^([a-z_]+:[a-z_]+|\*)$")


class CreateRoleRequest(BaseModel):
    """Create a custom role."""

    name: str = Field(min_length=1, max_length=64)
    permissions: list[str] = Field(min_length=1)
    ad_groups: list[str] = Field(min_length=1)
    area_scope: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _ROLE_NAME_RE.match(v):
            raise ValueError(
                "Role name must start with a letter and contain only letters, "
                "digits or underscores."
            )
        return v

    @field_validator("permissions", mode="before")
    @classmethod
    def _validate_permissions(cls, v: list) -> list:
        for p in v:
            if not isinstance(p, str) or not p.strip():
                raise ValueError("Each permission must be a non-empty string.")
            if not _PERMISSION_RE.match(p):
                raise ValueError(
                    f"Permission '{p}' must be '*' or in 'resource:action' format "
                    f"(e.g. 'user:read')."
                )
        return v

    @field_validator("ad_groups", mode="before")
    @classmethod
    def _validate_ad_groups(cls, v: list) -> list:
        for g in v:
            if not isinstance(g, str) or not g.strip():
                raise ValueError("Each AD group must be a non-empty string.")
        return v


class UpdateRoleRequest(BaseModel):
    """Update a custom role. Omitted fields are left unchanged."""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    permissions: list[str] | None = None
    ad_groups: list[str] | None = None
    area_scope: list[str] | None = None
    clear_area_scope: bool = Field(
        default=False, description="Set true to clear area_scope back to full-plant."
    )

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _ROLE_NAME_RE.match(v):
            raise ValueError(
                "Role name must start with a letter and contain only letters, "
                "digits or underscores."
            )
        return v

    @field_validator("permissions", mode="before")
    @classmethod
    def _validate_permissions(cls, v: list | None) -> list | None:
        if v is None:
            return v
        for p in v:
            if not isinstance(p, str) or not p.strip():
                raise ValueError("Each permission must be a non-empty string.")
            if not _PERMISSION_RE.match(p):
                raise ValueError(
                    f"Permission '{p}' must be '*' or in 'resource:action' format "
                    f"(e.g. 'user:read')."
                )
        return v

    @field_validator("ad_groups", mode="before")
    @classmethod
    def _validate_ad_groups(cls, v: list | None) -> list | None:
        if v is None:
            return v
        for g in v:
            if not isinstance(g, str) or not g.strip():
                raise ValueError("Each AD group must be a non-empty string.")
        return v


class RoleResponse(BaseModel):
    """The role representation returned to clients."""

    id: str
    name: str
    is_custom: bool
    permissions: list[str]
    ad_groups: list[str]
    area_scope: list[str] | None
    created_at: str
    updated_at: str

    @staticmethod
    def of(r: Role) -> "RoleResponse":
        return RoleResponse(
            id=r.id,
            name=r.name,
            is_custom=r.is_custom,
            permissions=r.permissions,
            ad_groups=r.ad_groups,
            area_scope=r.area_scope,
            created_at=r.created_at.isoformat(),
            updated_at=r.updated_at.isoformat(),
        )


class RoleMappingEntryResponse(BaseModel):
    """One AD-group-to-role mapping row, for the administration screen (BE-US002-2)."""

    ad_group: str
    role_id: str
    role_name: str
    is_custom: bool
    area_scope: list[str] | None

    @staticmethod
    def of(m: GroupRoleMapping) -> "RoleMappingEntryResponse":
        return RoleMappingEntryResponse(
            ad_group=m.ad_group,
            role_id=m.role_id,
            role_name=m.role_name,
            is_custom=m.is_custom,
            area_scope=m.area_scope,
        )
