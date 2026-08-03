"""Use case: find every pending action that is overdue (ES-353)."""

from src.application.pending_actions.repository import ActionFilter, PendingActionRepository
from src.domain.pending_actions.entities import PendingAction


async def find_overdue_actions(repo: PendingActionRepository) -> list[PendingAction]:
    """Every action past its due date and not yet in a terminal state.

    Reuses ``PendingAction.is_overdue()`` — already the single source of truth for what
    "overdue" means — rather than re-deriving the rule at the query layer, so this stays
    correct automatically if that domain rule ever changes.
    """
    actions = await repo.list(ActionFilter())
    return [a for a in actions if a.is_overdue()]
