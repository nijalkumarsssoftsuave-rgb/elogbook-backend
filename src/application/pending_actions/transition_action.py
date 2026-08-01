"""Use case: transition a pending action through its lifecycle."""

from src.api.errors.exceptions import NotFoundError
from src.application.audit.recorder import AuditEntry, AuditRecorder
from src.application.pending_actions.repository import PendingActionRepository
from src.domain.pending_actions.entities import PendingAction, PendingActionStatus
from src.domain.pending_actions.state_machine import apply_transition


async def transition_action(
    repo: PendingActionRepository,
    action_id: str,
    target: PendingActionStatus,
    audit: AuditRecorder | None = None,
    actor: str = "system",
) -> PendingAction:
    """Load, validate the transition (domain rule), apply and persist.

    Raises ``NotFoundError`` if the action is unknown and ``IllegalTransitionError``
    (mapped to 409) if the transition is not permitted from the current state. When an
    ``audit`` recorder is supplied the state change is recorded (from -> to) in the same
    unit of work.
    """
    action = await repo.get(action_id)
    if action is None:
        raise NotFoundError(f"Pending action {action_id} was not found.")
    from_status = action.status
    apply_transition(action, target)
    updated = await repo.update(action)
    if audit is not None:
        await audit.record(
            AuditEntry(
                actor=actor,
                action="pending_action.transition",
                entity_type="pending_action",
                entity_id=updated.id,
                payload={"from": from_status.value, "to": updated.status.value},
            )
        )
    return updated
