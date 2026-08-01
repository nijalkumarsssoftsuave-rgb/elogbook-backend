"""Use case: a Supervisor confirms an AI-suggested candidate as a real action (ES-343).

ES-341's extraction is stateless — candidates are never persisted, so there is no
server-side candidate to reference by id. This is the other half of the "suggested by
ai-service, confirmed by a supervisor" flow (see ``Source.AI_EXTRACTED``): the caller's
own accepted candidate fields come back in, a real ``PendingAction`` is created with
``source`` forced to ``ai`` (never caller-controlled — that's the whole point of this
endpoint existing separately from plain capture), and the audit trail records the
inclusion decision distinctly from an ordinary manual capture.
"""

from src.application.audit.recorder import AuditEntry, AuditRecorder
from src.application.pending_actions.repository import PendingActionRepository
from src.domain.pending_actions.entities import PendingAction, Priority, Source


async def confirm_inclusion(
    repo: PendingActionRepository,
    issue: str,
    priority: Priority,
    area: str | None = None,
    equipment: str | None = None,
    audit: AuditRecorder | None = None,
    actor: str = "system",
) -> PendingAction:
    """Persist a Supervisor-confirmed, AI-sourced candidate as a real pending action."""
    action = PendingAction.create(
        issue=issue,
        priority=priority,
        source=Source.AI_EXTRACTED,
        area=area,
        equipment=equipment,
    )
    stored = await repo.add(action)
    if audit is not None:
        await audit.record(
            AuditEntry(
                actor=actor,
                action="pending_action.confirm_inclusion",
                entity_type="pending_action",
                entity_id=stored.id,
                payload={
                    "issue": stored.issue,
                    "priority": stored.priority.value,
                    "status": stored.status.value,
                    "source": stored.source.value,
                    "area": stored.area,
                    "equipment": stored.equipment,
                },
            )
        )
    return stored
