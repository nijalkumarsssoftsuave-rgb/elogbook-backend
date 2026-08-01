"""Use case: confirmed pending actions captured during one shift (ES-344).

"Confirmed" here means a real, persisted ``PendingAction`` — manually captured or
Supervisor-confirmed via ES-343 — as opposed to an unconfirmed AI candidate from ES-341,
which is never persisted at all. Both origins count: a shift-level report needs
everything that actually happened during the shift, not just one source.
"""

from src.application.pending_actions.repository import ActionFilter, PendingActionRepository
from src.domain.pending_actions.entities import PendingAction
from src.domain.shifts.entities import Shift


async def get_actions_for_shift(repo: PendingActionRepository, shift: Shift) -> list[PendingAction]:
    """Every confirmed action whose ``created_at`` falls inside ``shift``'s window."""
    return await repo.list(ActionFilter(created_from=shift.starts_at, created_to=shift.ends_at))
