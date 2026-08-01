"""Pending-action repository port.

Defined in the application layer, implemented in infrastructure and injected — the
clean-architecture dependency rule. The MS SQL adapter drops in behind this same
interface without touching the use cases.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

from src.domain.pending_actions.entities import (
    PendingAction,
    PendingActionStatus,
    Priority,
    Source,
)


@dataclass
class ActionFilter:
    """Optional filters for listing pending actions (BRD FR-PA-03, ES-348).

    ``created_from``/``created_to`` bound by ``created_at`` (``>=``/``<``) — used by the
    shift-actions report (ES-344) to scope actions to one shift's window, but generic
    enough for any date-range listing. ``created_at`` is always stored tz-aware UTC
    (``PendingAction.create``), so a naive value here — e.g. a caller passing a
    timezone-less ISO string via the ``GET /pending-actions`` query params — would
    otherwise crash the in-memory backend's ``>=``/``<`` comparison with
    ``TypeError: can't compare offset-naive and offset-aware datetimes``. Normalising
    here, not per-caller, protects every current and future caller uniformly.
    """

    status: PendingActionStatus | None = None
    owner: str | None = None
    area: str | None = None
    equipment: str | None = None
    priority: Priority | None = None
    source: Source | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_from is not None and self.created_from.tzinfo is None:
            self.created_from = self.created_from.replace(tzinfo=UTC)
        if self.created_to is not None and self.created_to.tzinfo is None:
            self.created_to = self.created_to.replace(tzinfo=UTC)


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
