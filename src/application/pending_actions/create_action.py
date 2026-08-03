"""Use case: capture a pending action."""

from datetime import date

from src.application.audit.recorder import AuditEntry, AuditRecorder
from src.application.pending_actions.repository import PendingActionRepository
from src.domain.pending_actions.entities import PendingAction, Priority, Source


async def capture_action(
    repo: PendingActionRepository,
    issue: str,
    priority: Priority,
    source: Source,
    area: str | None = None,
    equipment: str | None = None,
    owner: str | None = None,
    due_date: date | None = None,
    audit: AuditRecorder | None = None,
    actor: str = "system",
    audit_action: str = "pending_action.create",
) -> PendingAction:
    """Create and persist a new pending action in the OPEN state.

    When an ``audit`` recorder is supplied the capture is written to the immutable trail
    in the same unit of work, so the action and its audit entry are committed together.
    ``audit_action`` lets a distinct caller (``confirm_inclusion``, ES-343) record this as
    its own event type rather than an indistinguishable ``pending_action.create`` — the
    create/persist/audit-payload shape is otherwise identical regardless of who called it.
    """
    action = PendingAction.create(
        issue=issue,
        priority=priority,
        source=source,
        area=area,
        equipment=equipment,
        owner=owner,
        due_date=due_date,
    )
    stored = await repo.add(action)
    if audit is not None:
        await audit.record(
            AuditEntry(
                actor=actor,
                action=audit_action,
                entity_type="pending_action",
                entity_id=stored.id,
                payload={
                    "issue": stored.issue,
                    "priority": stored.priority.value,
                    "status": stored.status.value,
                    "source": stored.source.value,
                    "area": stored.area,
                    "equipment": stored.equipment,
                    "owner": stored.owner,
                    "due_date": stored.due_date,
                },
            )
        )
    return stored
