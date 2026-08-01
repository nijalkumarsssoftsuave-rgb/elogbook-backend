"""MS SQL / SQLAlchemy role repository.

Implements the ``RoleRepository`` port with SQLAlchemy Core over one injected
``AsyncSession``. Mutating methods do **not** commit — the unit of work owns the
transaction. Reads are simple full-table scans: the roles table holds a handful of rows
(base + admin-created custom roles), so filtering by AD group happens in Python rather
than with SQL-side JSON querying.
"""

import json
from typing import Any

from sqlalchemy import Row, delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.users_roles.repository import RoleRepository
from src.domain.users_roles.entities import Role
from src.infrastructure.persistence.tables import roles


def _to_values(role: Role) -> dict[str, Any]:
    return {
        "id": role.id,
        "name": role.name,
        "is_custom": role.is_custom,
        "permissions": json.dumps(role.permissions),
        "ad_groups": json.dumps(role.ad_groups),
        "area_scope": json.dumps(role.area_scope) if role.area_scope is not None else None,
        "created_at": role.created_at,
        "updated_at": role.updated_at,
    }


def _to_entity(row: Row) -> Role:
    m = row._mapping
    return Role(
        id=m["id"],
        name=m["name"],
        is_custom=bool(m["is_custom"]),
        permissions=json.loads(m["permissions"]),
        ad_groups=json.loads(m["ad_groups"]),
        area_scope=json.loads(m["area_scope"]) if m["area_scope"] is not None else None,
        created_at=m["created_at"],
        updated_at=m["updated_at"],
    )


class SqlRoleRepository(RoleRepository):
    """Persistence adapter over an injected async session (no autocommit)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Role]:
        result = await self._session.execute(select(roles).order_by(roles.c.name))
        return [_to_entity(row) for row in result.all()]

    async def get(self, role_id: str) -> Role | None:
        result = await self._session.execute(select(roles).where(roles.c.id == role_id))
        row = result.first()
        return _to_entity(row) if row is not None else None

    async def get_by_name(self, name: str) -> Role | None:
        result = await self._session.execute(select(roles).where(roles.c.name == name))
        row = result.first()
        return _to_entity(row) if row is not None else None

    async def get_for_groups(self, groups: list[str]) -> list[Role]:
        all_roles = await self.list_all()
        group_set = set(groups)
        return [r for r in all_roles if group_set & set(r.ad_groups)]

    async def add(self, role: Role) -> Role:
        await self._session.execute(insert(roles).values(**_to_values(role)))
        return role

    async def update(self, role: Role) -> Role:
        values = _to_values(role)
        values.pop("id")
        await self._session.execute(update(roles).where(roles.c.id == role.id).values(**values))
        return role

    async def delete(self, role_id: str) -> None:
        await self._session.execute(delete(roles).where(roles.c.id == role_id))
