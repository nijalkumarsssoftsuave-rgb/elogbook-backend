"""Shift-configuration repository port.

Defined in the application layer, implemented in infrastructure and injected — the
clean-architecture dependency rule. Append-only (US-008): a config change always
inserts a new effective-dated version, so the port exposes no update/delete.
"""

from abc import ABC, abstractmethod

from src.domain.shifts.entities import ShiftConfiguration


class ShiftConfigRepository(ABC):
    """Persistence contract for shift configurations."""

    @abstractmethod
    async def list_all(self) -> list[ShiftConfiguration]: ...

    @abstractmethod
    async def get(self, config_id: str) -> ShiftConfiguration | None: ...

    @abstractmethod
    async def add(self, config: ShiftConfiguration) -> ShiftConfiguration: ...
