"""User / identity request and response schemas."""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from src.domain.users_roles.entities import User

_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
# Admin user CRUD schemas (ES-358 / ES-359)
# ---------------------------------------------------------------------------


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    email: str = Field(min_length=5, max_length=256)
    role_id: str | None = None

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not _USERNAME_RE.match(v):
            raise ValueError(
                "Username must start with a letter or digit and contain only "
                "letters, digits, dots, hyphens or underscores."
            )
        return v

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("display_name must not be blank.")
        return v

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("email must be a valid address (e.g. user@domain.com).")
        return v


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=256)
    email: str | None = Field(default=None, max_length=256)
    role_id: str | None = None
    clear_role: bool = False  # True → set role_id to None regardless of role_id field
    is_active: bool | None = None

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("display_name must not be blank.")
        return v

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("email must be a valid address (e.g. user@domain.com).")
        return v


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
