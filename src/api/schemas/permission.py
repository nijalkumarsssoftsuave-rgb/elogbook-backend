"""Permission catalogue response schema."""

from pydantic import BaseModel

from src.domain.users_roles.permissions import PermissionEntry


class PermissionEntryResponse(BaseModel):
    permission: str
    module: str
    description: str

    @staticmethod
    def of(e: PermissionEntry) -> "PermissionEntryResponse":
        return PermissionEntryResponse(
            permission=e.permission,
            module=e.module,
            description=e.description,
        )
