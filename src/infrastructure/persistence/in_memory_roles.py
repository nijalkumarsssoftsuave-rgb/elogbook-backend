"""In-memory role repository — the default local/test backend.

Seeded with the five base roles so default behaviour (group -> role -> permissions) is
identical to what the old hardcoded dictionaries did; custom roles created through the
admin API just live in this process for the life of the run.
"""

import copy

from src.application.users_roles.repository import RoleRepository
from src.domain.users_roles.entities import Role
from src.domain.users_roles.seed import BASE_ROLES


class InMemoryRoleRepository(RoleRepository):
    """Process-local store. Not for production — replaced by the MS SQL adapter."""

    def __init__(self) -> None:
        self._items: dict[str, Role] = {r.id: copy.deepcopy(r) for r in BASE_ROLES}

    async def list_all(self) -> list[Role]:
        return sorted(self._items.values(), key=lambda r: r.name)

    async def get(self, role_id: str) -> Role | None:
        return self._items.get(role_id)

    async def get_by_name(self, name: str) -> Role | None:
        return next((r for r in self._items.values() if r.name == name), None)

    async def get_for_groups(self, groups: list[str]) -> list[Role]:
        group_set = set(groups)
        return [r for r in self._items.values() if group_set & set(r.ad_groups)]

    async def add(self, role: Role) -> Role:
        self._items[role.id] = role
        return role

    async def update(self, role: Role) -> Role:
        self._items[role.id] = role
        return role

    async def delete(self, role_id: str) -> None:
        self._items.pop(role_id, None)
