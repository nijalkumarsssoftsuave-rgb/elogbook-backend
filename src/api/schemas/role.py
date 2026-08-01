"""Role request/response schemas (admin role management)."""

from pydantic import BaseModel, Field, field_validator

from src.application.admin.manage_roles import GroupRoleMapping
from src.domain.users_roles.entities import Role


class CreateRoleRequest(BaseModel):
    """Create a custom role."""

    name: str = Field(min_length=1, max_length=64)
    permissions: list[str] = Field(min_length=1)
    ad_groups: list[str] = Field(min_length=1)
    area_scope: list[str] | None = None

    @field_validator("area_scope", mode="before")
    @classmethod
    def _validate_area_scope(cls, v: list | None) -> list | None:
        if v is None:
            return v
        for a in v:
            if not isinstance(a, str) or not a.strip():
                raise ValueError("Each area must be a non-empty string.")
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

    @field_validator("area_scope", mode="before")
    @classmethod
    def _validate_area_scope(cls, v: list | None) -> list | None:
        if v is None:
            return v
        for a in v:
            if not isinstance(a, str) or not a.strip():
                raise ValueError("Each area must be a non-empty string.")
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
