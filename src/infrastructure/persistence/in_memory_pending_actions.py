"""In-memory pending-action repository.

A working adapter so the full feature runs and is tested now, before MS SQL is
available (Tracker A-04). Implements the same port the MS SQL repository will, so the
use cases and API are unchanged when persistence is swapped in.
"""

from src.application.pending_actions.repository import ActionFilter, PendingActionRepository
from src.domain.pending_actions.entities import PendingAction


class InMemoryPendingActionRepository(PendingActionRepository):
    """Process-local store. Not for production — replaced by the MS SQL adapter."""

    def __init__(self) -> None:
        self._items: dict[str, PendingAction] = {}

    async def add(self, action: PendingAction) -> PendingAction:
        self._items[action.id] = action
        return action

    async def get(self, action_id: str) -> PendingAction | None:
        return self._items.get(action_id)

    async def update(self, action: PendingAction) -> PendingAction:
        self._items[action.id] = action
        return action

    async def list(self, filters: ActionFilter) -> list[PendingAction]:
        def matches(a: PendingAction) -> bool:
            return (
                (filters.status is None or a.status == filters.status)
                and (filters.owner is None or a.owner == filters.owner)
                and (filters.area is None or a.area == filters.area)
                and (filters.equipment is None or a.equipment == filters.equipment)
                and (filters.priority is None or a.priority == filters.priority)
                and (filters.source is None or a.source == filters.source)
                and (filters.created_from is None or a.created_at >= filters.created_from)
                and (filters.created_to is None or a.created_at < filters.created_to)
            )

        return sorted(
            (a for a in self._items.values() if matches(a)),
            key=lambda a: a.created_at,
            reverse=True,
        )
