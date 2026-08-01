"""Role repository port.

Defined in the application layer, implemented in infrastructure and injected — the
clean-architecture dependency rule. Both the token-validation path (resolving a user's
roles from their AD groups) and the admin role-management use cases go through this
same interface.
"""

from abc import ABC, abstractmethod

from src.domain.users_roles.entities import Role, User


class RoleRepository(ABC):
    """Persistence contract for roles."""

    @abstractmethod
    async def list_all(self) -> list[Role]: ...

    @abstractmethod
    async def get(self, role_id: str) -> Role | None: ...

    @abstractmethod
    async def get_by_name(self, name: str) -> Role | None: ...

    @abstractmethod
    async def get_for_groups(self, groups: list[str]) -> list[Role]:
        """Every role mapped from any of the given AD groups (multi-role union)."""
        ...

    @abstractmethod
    async def add(self, role: Role) -> Role: ...

    @abstractmethod
    async def update(self, role: Role) -> Role: ...

    @abstractmethod
    async def delete(self, role_id: str) -> None: ...


class UserRepository(ABC):
    """Persistence contract for admin-managed users."""

    @abstractmethod
    async def list_all(self) -> list[User]: ...

    @abstractmethod
    async def get(self, user_id: str) -> User | None: ...

    @abstractmethod
    async def get_by_username(self, username: str) -> User | None: ...

    @abstractmethod
    async def add(self, user: User) -> User: ...

    @abstractmethod
    async def update(self, user: User) -> User: ...

    @abstractmethod
    async def delete(self, user_id: str) -> None: ...

    @abstractmethod
    async def count_by_role_id(self, role_id: str) -> int:
        """How many users currently have this role assigned (used for delete-conflict guard)."""
        ...
