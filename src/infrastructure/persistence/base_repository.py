"""Repository interface (port).

Engineering Code Standards, discipline 5: data access sits behind repository
interfaces; the application layer depends on this abstraction, and a concrete MS SQL
implementation (repositories.py) is injected. Concrete methods are TODO.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")
ID = TypeVar("ID")


class Repository(ABC, Generic[T, ID]):
    """Minimal repository contract shared by all persistence adapters."""

    @abstractmethod
    async def get(self, id_: ID) -> T | None:
        """Fetch a single aggregate by id, or None."""
        raise NotImplementedError

    @abstractmethod
    async def add(self, entity: T) -> T:
        """Persist a new aggregate."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, entity: T) -> T:
        """Persist changes to an existing aggregate."""
        raise NotImplementedError
