"""Pending-action lifecycle state machine — pure domain rules.

Open -> In Progress -> On Hold -> Completed -> Verified, with Cancelled reachable from
any non-terminal state (BRD: "Any state may move to Cancelled"). Cancelled and Verified
are terminal.
"""

from src.domain.pending_actions.entities import PendingAction
from src.domain.pending_actions.entities import PendingActionStatus as S

# allowed forward transitions (Cancelled is added to every non-terminal state below)
_ALLOWED: dict[S, set[S]] = {
    S.OPEN: {S.IN_PROGRESS, S.ON_HOLD},
    S.IN_PROGRESS: {S.ON_HOLD, S.COMPLETED},
    S.ON_HOLD: {S.IN_PROGRESS, S.COMPLETED},
    S.COMPLETED: {S.VERIFIED},
    S.VERIFIED: set(),
    S.CANCELLED: set(),
}

_TERMINAL = {S.VERIFIED, S.CANCELLED}


class IllegalTransitionError(Exception):
    """Raised when a transition is not permitted from the current state."""

    def __init__(self, current: S, target: S) -> None:
        super().__init__(f"Cannot move a pending action from {current.value} to {target.value}.")
        self.current = current
        self.target = target


def allowed_targets(current: S) -> set[S]:
    """The states reachable from ``current``."""
    if current in _TERMINAL:
        return set()
    return _ALLOWED[current] | {S.CANCELLED}


def can_transition(current: S, target: S) -> bool:
    """True if moving from ``current`` to ``target`` is permitted."""
    return target in allowed_targets(current)


def apply_transition(action: PendingAction, target: S) -> PendingAction:
    """Apply a validated transition to the action, or raise ``IllegalTransitionError``."""
    if not can_transition(action.status, target):
        raise IllegalTransitionError(action.status, target)
    action.status = target
    action.touch()
    return action
