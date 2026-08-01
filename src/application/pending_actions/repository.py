"""Pending-action repository port.

Defined in the application layer, implemented in infrastructure and injected — the
clean-architecture dependency rule. The MS SQL adapter drops in behind this same
interface without touching the use cases.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.pending_actions.entities import PendingAction, PendingActionStatus, Priority


@dataclass
class ActionFilter:
    """Optional filters for listing pending actions (BRD FR-PA-03)."""

    status: PendingActionStatus | None = None
    owner: str | None = None
    area: str | None = None
    equipment: str | None = None
    priority: Priority | None = None


class PendingActionRepository(ABC):
    """Persistence contract for pending actions."""

    @abstractmethod
    async def add(self, action: PendingAction) -> PendingAction: ...

    @abstractmethod
    async def get(self, action_id: str) -> PendingAction | None: ...

    @abstractmethod
    async def update(self, action: PendingAction) -> PendingAction: ...

    @abstractmethod
    async def list(self, filters: ActionFilter) -> list[PendingAction]: ...
