"""MS SQL / SQLAlchemy user repository.

Implements the ``UserRepository`` port with SQLAlchemy Core over one injected
``AsyncSession``. Mutating methods do **not** commit — the unit of work owns the
transaction.
"""

from typing import Any

from sqlalchemy import Row, delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.users_roles.repository import UserRepository
from src.domain.users_roles.entities import User
from src.infrastructure.persistence.tables import users


def _to_values(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "is_active": user.is_active,
        "role_id": user.role_id,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _to_entity(row: Row) -> User:
    m = row._mapping
    return User(
        id=m["id"],
        username=m["username"],
        display_name=m["display_name"],
        email=m["email"],
        is_active=bool(m["is_active"]),
        role_id=m["role_id"],
        created_at=m["created_at"],
        updated_at=m["updated_at"],
    )


class SqlUserRepository(UserRepository):
    """Persistence adapter over an injected async session (no autocommit)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[User]:
        result = await self._session.execute(select(users).order_by(users.c.username))
        return [_to_entity(row) for row in result.all()]

    async def get(self, user_id: str) -> User | None:
        result = await self._session.execute(select(users).where(users.c.id == user_id))
        row = result.first()
        return _to_entity(row) if row is not None else None

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(
            select(users).where(users.c.username == username.lower())
        )
        row = result.first()
        return _to_entity(row) if row is not None else None

    async def add(self, user: User) -> User:
        await self._session.execute(insert(users).values(**_to_values(user)))
        return user

    async def update(self, user: User) -> User:
        values = _to_values(user)
        values.pop("id")
        await self._session.execute(
            update(users).where(users.c.id == user.id).values(**values)
        )
        return user

    async def delete(self, user_id: str) -> None:
        await self._session.execute(delete(users).where(users.c.id == user_id))

    async def count_by_role_id(self, role_id: str) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(users).where(users.c.role_id == role_id)
        )
        return result.scalar_one_or_none() or 0
