"""User / identity request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, field_validator

from src.domain.users_roles.entities import User


class UserProfile(BaseModel):
    """The payload returned by GET /me."""

    subject: str
    username: str
    display_name: str
    roles: list[str]
    groups: list[str]
    permissions: list[str]
    area_scope: list[str] | None = None


# ---------------------------------------------------------------------------
# Admin user CRUD schemas (ES-358)
# ---------------------------------------------------------------------------


class CreateUserRequest(BaseModel):
    username: str
    display_name: str
    email: str
    role_id: str | None = None

    @field_validator("username")
    @classmethod
    def _normalise_username(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, v: str) -> str:
        return v.strip().lower()


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    role_id: str | None = None
    clear_role: bool = False  # True → set role_id to None regardless of role_id field
    is_active: bool | None = None


class AdminUserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    email: str
    is_active: bool
    role_id: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, user: User) -> "AdminUserResponse":
        return cls(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            is_active=user.is_active,
            role_id=user.role_id,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
