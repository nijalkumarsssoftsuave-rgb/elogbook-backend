"""User / identity response schemas."""

from pydantic import BaseModel


class UserProfile(BaseModel):
    """The payload returned by GET /me."""

    subject: str
    username: str
    display_name: str
    roles: list[str]
    groups: list[str]
    permissions: list[str]
    area_scope: list[str] | None = None
