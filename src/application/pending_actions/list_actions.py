"""Use cases: list and fetch pending actions."""

from src.application.pending_actions.repository import ActionFilter, PendingActionRepository
from src.domain.pending_actions.entities import PendingAction


async def list_actions(repo: PendingActionRepository, filters: ActionFilter) -> list[PendingAction]:
    """Return pending actions matching the filters, newest first."""
    return await repo.list(filters)


async def get_action(repo: PendingActionRepository, action_id: str) -> PendingAction | None:
    """Return a single pending action, or None."""
    return await repo.get(action_id)
