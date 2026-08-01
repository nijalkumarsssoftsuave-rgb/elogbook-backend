"""In-memory user repository — the default local/test backend.

Starts empty (no pre-seeded users). Admin API calls populate it for the life of the
process run.
"""

import copy

from src.application.users_roles.repository import UserRepository
from src.domain.users_roles.entities import User


class InMemoryUserRepository(UserRepository):
    """Process-local store. Not for production — replaced by the MS SQL adapter."""

    def __init__(self) -> None:
        self._items: dict[str, User] = {}

    async def list_all(self) -> list[User]:
        return sorted(self._items.values(), key=lambda u: u.username)

    async def get(self, user_id: str) -> User | None:
        item = self._items.get(user_id)
        return copy.deepcopy(item) if item is not None else None

    async def get_by_username(self, username: str) -> User | None:
        lower = username.lower()
        match = next((u for u in self._items.values() if u.username == lower), None)
        return copy.deepcopy(match) if match is not None else None

    async def add(self, user: User) -> User:
        self._items[user.id] = user
        return user

    async def update(self, user: User) -> User:
        self._items[user.id] = user
        return user

    async def delete(self, user_id: str) -> None:
        self._items.pop(user_id, None)
